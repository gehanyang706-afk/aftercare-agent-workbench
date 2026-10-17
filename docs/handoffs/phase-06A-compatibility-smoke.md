# 阶段 6A：compatibility-smoke 已完成

只完成这一个获批批次；阶段 6A 的 development-pilot、6B 正式对照仍未授权。
实际 6 次 HTTP、0 重试、6/6 检查通过；输入 1,001、输出 101，总量 1,102 Token，未知预留 0；耗时 13.933 秒。
逐项结果、问题和限制见 docs/experiments/compatibility-smoke.md / .json。
工作台和 worker 仍为阶段 5 的离线镜像，不代表已接通真实业务 Agent。

## 命令与证据

本轮已执行（不要重复执行；相同批次再次启动会被拒绝）：

```bash
ALLOW_REAL_MODEL_CALLS=true .venv/bin/python -m aftercare model smoke \
  --batch compatibility-smoke --approval runtime/phase-06A/approval.json \
  --account-confirmation runtime/phase-06A/account-confirmation.json --execute
```

退出码 0。Key 只从本机 .env 读取，真实开关仅对该进程启用；.env 默认仍 false。
原始响应/账本核对/状态/审批与账户确认在 runtime/phase-06A，不进 Git。公开摘要不含凭据或账户地址。
全量离线：AFTERCARE_TEST_DATABASE_URL 指定 aftercare_test 后运行 `pytest -m 'not live_model'`，
**66 passed，0 skipped，28.05s**；offline-tests.log / offline-junit.xml。
新增 6 项测试覆盖正常 6 请求、重启拒绝、未知 usage/HTTP 错误、协议失败、硬截止、授权/计划篡改和流式完整性。
ruff check、format、diff check 均通过；真实模型不属于普通回归测试。

## 数据流与完整机制

用户批准 + 计划 hash + 账户确认 → CLI 专用入口校验 → PostgreSQL 会话锁与持久批次状态 →
BudgetLedger 请求前预留 → 有界子进程仅向已核对的 HTTPS 域名发送一次 →
收集完整响应/流式末块 usage → 先结算用量，再判协议结果 → 任何异常停止 → 原始记录与只读对账。

“业务结果和消费事实分开”：即使响应内容不合格，只要 usage 完整仍须结算真实消费；
若用量不明，保留整笔预留、暂停该模型批次，不能按零释放。
每个发送尝试在网络前落账；没有隐式重试、重定向或自动换模型。网络失败时尝试数按保守上界记录，
不伪称已经知道服务端是否收到了请求。持久状态存在则禁止直接重跑，防止新进程重置请求计数。

五个入口：src/aftercare/llm/smoke.py；llm/budget.py；llm/supervisor.py；cli.py；tests/agent_contract/test_smoke.py。
普通 provider factory 与通用 Agent 的真实发送入口仍拒绝调用；此实现只开放冻结的六项兼容 fixture。

## 状态、决定与下一步

已实现/已验证：严格单批入口、一次请求传输、真实 usage 与 request_id、流式末块处理、独立硬截止、持久预算和对账。
待验证：完整九工具真实 Agent、语言理解、真实场景的用量和恢复、严格结构化输出能力、账单核对。
未授权/未执行：development-pilot、正式对照、模型用户、独立 holdout。独立答案仍未读取。
真实批次无故障或重试；发送前修正原生 Base URL 路径，不改变获批请求正文。
官方参数与地域依据列在实验报告，账户保护由用户确认，未声称程序独立核验控制台。

下一批具体计划在 evaluation/manifests/development-pilot.json：4 个已见 dev 任务，同模型，full，脚本用户，
每题 24k/16 请求，总 96k/64 请求，并发 1，最长 20 分钟，额外付费 0。
这是上限而非实际预测。未获批前不能发送；不将本批剩余次数或 Token 挪过去。

体验任务：从一个 request_id 对上原始 usage 与数据库结算，比较预留与实际消费。
三个问题：为什么协议失败也可能收费？为什么未知 usage 不能计零？为什么重启不能获得新的 8 次额度？
