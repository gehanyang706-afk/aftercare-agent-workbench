# 阶段 3：单主 Agent、HITL 与预算网关

已接入安装的 Deep Agents 0.7.28 / LangGraph / PostgresSaver。检查了实际源码与签名，
使用 HarnessProfile 关闭默认 general-purpose subagent 和 SummarizationMiddleware；无自动摘要调用。
文件 backend 仅默认隔离 StateBackend；模型可见与执行层均强制九个业务工具白名单，无开放 shell/文件/task。

## 运行与实际验证

在项目根目录，先 db migrate（同时 setup 正式 checkpoint 表），demo seed。每次 demo 前可显式 reset demo-only：

```bash
.venv/bin/python -m aftercare db migrate
.venv/bin/python -m aftercare demo reset --confirm demo-only
.venv/bin/python -m aftercare demo run --case agent-exchange --provider scripted
.venv/bin/python -m aftercare demo reset --confirm demo-only
.venv/bin/python -m aftercare demo run --case revise-before-confirm --provider scripted
.venv/bin/python -m aftercare demo reset --confirm demo-only
.venv/bin/python -m aftercare demo run --case restart-after-commit --provider scripted
AFTERCARE_TEST_DATABASE_URL=postgresql+psycopg://aftercare:aftercare_local_only@127.0.0.1:55432/aftercare_test .venv/bin/python -m pytest tests/unit tests/integration tests/agent_contract tests/retrieval
```

最后一条实测 **48 passed，0 skipped**、退出码 0，包含已授权的真实本地 ONNX 权重、正式 PostgreSQL。
证据 runtime/phase-03/tests.log / junit.xml。静态检查/格式检查通过。demo 实际输出保存在同目录。
实际白名单断言覆盖 list_orders/get_order/get_inventory/search_policies/update_case/preview_action/
commit_action/get_operation/request_handoff，所有 tool_call_id 与回复成对，包括并行工具和错误。

## 数据流与一个完整机制

用户消息先写业务库/增加 intent_revision/使旧预览失效 → 主图使用 ScriptedModel 产生工具 JSON →
Pydantic 严格校验并注入服务端身份 → 工具调用业务/检索服务 → preview → commit_action 前持久化中断 →
可信确认入口写 Approval → 同 thread 的 Command 恢复 → 后端再验证 Approval/版本 → 事务提交 → 回执。

checkpoint 只记录“图停在哪里”。重启重建 graph 时可停留在原 commit_action；若业务事务先提交、checkpoint
尚未推进，重复恢复会再次进入工具，但 preview 唯一 operation 只返回原回执。
反过来，直接给图 approve 而不写业务 Approval，后端会拒绝；框架批准不能伪造用户授权。
新普通消息到达后先拒绝旧中断，补全其 tool reply，再处理新消息；旧图不会带着旧授权执行新参数。

五个入口：agent/runtime.py；agent/tools.py；agent/middleware.py；llm/scripted.py；llm/budget.py。
端到端硬截止辅助入口 llm/supervisor.py：独立子进程执行，阻塞替身不配合 SDK timeout 也会被终止并回收。

## 预算与能力边界

模型请求前按完整 system/history/tool schema/参数的 UTF-8 字节上界加余量+输出 cap 在 PostgreSQL 预留；
项目、精确 provider/model/batch 预算行加锁，记录每次请求、usage、request_id 与状态。
每轮最多 8 次、会话最多 16 次；参数错误最多两次，读重试最多两次，工具总数有界。
usage 不明保留预留、暂停同模型；不得当零。并发预留不能超支，满额时模型调用次数仍为 0。
ScriptedModel 的 usage 是明确标记的合成计数，真实费用为 0；不能用它估计真实模型账单。
BailianAdapter 只做精确模型请求构造及离线快照校验，真正发送仍无条件禁用。
Qwen/GLM 参数写 configs/models.yaml，均标记 offline-request-shape-only，不称账户兼容性已验证。
真实输入上界也不能代替服务商保护；阶段 6 前仍须单独批准具体批次。

## 实际缺陷、状态与限制

契约测试发现 LangGraph 工具节点会吞掉 Pydantic 参数异常，返回带原始参数的普通文本；
修复为在业务边界提前严格校验，返回统一错误 envelope 并记录 invalid_tool_attempt，保留 call/result 配对。
重试和清理有界；没有把失败响应假装成空列表或成功。

已实现/已验证：工具循环、并行结果、schema/白名单、持久化确认、重启、提交/checkpoint 间隙、改口、预算并发、未知用量、阻塞清理。
待真实模型验证：理解/工具选择/服务商协议/usage/流式计费，尚无真实推理请求。
未实现：Web、数据库 job 租约、SSE、浏览器恢复、独立业务评测；下一阶段补齐。
脚本模型只是通用演示规则，不是自然语言 LLM，不硬编码开发任务 ID 或答案。

体验任务：跑改口 demo，核对旧 preview INVALIDATED、新预览需独立确认及最终 operation。
三个问题：模型 JSON 如何进入服务事务？图 approve 为何不等于业务批准？未知用量为什么不能释放预留？
下一阶段：三栏 Web、可信会话/CSRF、数据库任务队列与 worker 进程监督、SSE 重放和浏览器检查；继续默认离线。
