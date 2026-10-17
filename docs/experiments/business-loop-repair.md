# 真实业务闭环修复与回归准备（离线）

本次真实请求 **0**，真实输入/输出 Token **0/0**，未知预留 **0**。未运行 holdout、架构对照或创建新审批。
原题、首轮 **0/4**、53 份原始 JSON、四题 regression-v1 与冻结评分器逐字保留，hash 核对通过。
持久真实账本仍只有旧兼容批 6 请求/1,102 Token 与首轮 pilot 24 请求/49,871 Token。

## 版本和实际验证

- 代码提交：41a28d4581f58dc67a0bba478b3df6020db13127。
- 源码/测试/配置指纹：1fdd39ef10757ad5d9f8f1fed070697b94191996d9f9467d3739b3bfe41be281。
- 场景：regression-v1.jsonl 四题原文件；新增 quantity-clarification-v1.jsonl 两题，均为已见开发回归。
- 用户策略 script-user-v2；旁路诊断 process-diagnostic-v2；评分器未改，hash：c3c2bbb07956ad4f8f3b629522a0fab4bf981649113c6ce601e31f030057fc3a。
- 全量离线测试：**118 passed / 0 skipped / 0 failed，18.66 秒**。
- 六题在固定代码上各运行一次，**6/6 通过冻结评分器**。脚本模型只证明工程链路，不代表真实模型质量。
- ruff check、format、git diff --check 通过。
- 保存修改前的 9 个门禁/幂等失败、4 个购买数量/撤回失败、4 个否定/应答失败；日志在 runtime/closure-repair/。
- 冻结清单：evaluation/manifests/closure-repair-freeze.json；详细事件与诊断：docs/experiments/business-loop-repair.json。
- 最终原始回归目录：/Users/gehanyang/编程/aftercare-agent-workbench/runtime/closure-repair/offline-20261018-002816。

## d-001 根因与最小修复

原轨迹：取消 S1001 → get_order → preview 创建 PENDING → update_case 无条件 INVALIDATED → commit 提议被 HITL 中断。
未产生有效卡片、可信确认或业务提交。f60c6e8 门禁仅在 middleware 检查 intent_revision；
它不能证明字段一致，且检查和预览创建不在同一事务。

保留九工具和单主图，修复如下：

1. Agent 预览在创建事务内检查 case/current revision、订单/动作/行/数量和实际用户证据。
   与 update_case、append_message 共用会话行锁。错误顺序返回 CASE_UPDATE_REQUIRED，明确要求补状态后重试预览。
2. 相同 revision、相同值的 update_case 是 no-op，不增加无意义 superseded，也不作废有效预览或确认。
   字段真实变化、新用户消息仍使旧方案失效；聊天“好的”也不替代可信确认。
3. 用户未说数量时，购买量、库存都不能充当申请量。购买/库存描述、否定、选项问题、普通应答不授权新动作。
   无法识别则澄清，不生成可确认预览。
4. 失效 commit 提议在 HITL 前记录参数及当时状态，返回配对错误；
   允许最多两次额外预算内模型修正请求，不制造正常确认流程。所有请求仍经原网关计费保护。
5. 服务端 confirmation_available 决定 UI 是否展示有效卡片；
   confirm/commit 继续校验身份、版本、hash、资格、政策、金额、库存和幂等，旧校验没有取消。

取舍：仍显式暴露“建立诉求后预览”的两工具依赖；服务层强制约束，Agent 根据错误继续，
不自动替模型补造事实。同批并发要么合法串行，要么可恢复地失败。
内部确定性 BusinessService.preview 保留可信服务调用兼容接口；
Agent 工具固定启用 require_case，Web 无绕过门禁的预览创建端点，没有整体重构架构。

## 逐题关键事件链

以下全部是**脚本模型离线证据**。每题真实 HTTP/输入 Token/输出 Token/未知预留均为 0/0/0/0。

| 任务 | 用户表达 → 有效诉求 → 预览 → 可信确认 → 提交 → 回执 → 告知 | 实际副作用 |
|---|---|---|
| r1-d-001 | 取消 S1001 → cancel/S1001 → 整单预览 → trusted-api → 原预览提交 → CANCELLED → 仅模拟退款请求 | 1 operation、1 模拟退款，非到账 |
| r1-d-003 | S1002 中 1 件换大一码 → exchange/1 → white-L/1/800 分 → trusted-api → 提交 → EXCHANGE_REQUESTED → 尚未退款或寄出 | 1 operation、1 application、占库存 1 |
| r1-d-016 | 换 1 件 → 换货预览 → 用户“改为退其中这 1 件” → revision 2/return/1 → 旧预览 INVALIDATED、新退货预览 → 仅新方案可信确认 → RETURN_REQUESTED → 仅申请 | 改口确实发生；旧方案未提交；仅 1 次退货副作用 |
| r1-d-048 | 换 1 件 → 有效预览 → 可信确认 → 事务提交成功 → 故意丢响应 → WRITE_RESULT_UNKNOWN → get_operation 查询同一预览/操作 → 原回执告知 | 故障真实发生；1 operation、1 application，无二次写入 |
| q1-A | 未说数量 → 有效诉求无申请数量 → 先问几件，无预览 → 用户实际回答“其中 1 件” → 新 revision/quantity 1 → 预览 → 可信确认 → 回执 → 告知 | 回答后才可确认；1 operation、1 application |
| q1-B | 未说数量 → 先问，无预览 → 用户答“全部 2 件” → quantity 2 → 库存仅 1，预览拒绝 → 解释缺货、问后续选择 → 用户保留 2 件等补货，暂不提交 → 告知未建申请/提醒 | 0 operation/application/退款，未改成 1 件或退货 |

- r1-d-001：离线 1.069 秒；正常 HITL 1，失效提交提议 0，缺确认执行 0，错误副作用 0，重复 0，未确认数量断言 0。
- r1-d-003：离线 0.978 秒；正常 HITL 1，失效提交提议 0，缺确认执行 0，错误副作用 0，重复 0，未确认数量断言 0。
- r1-d-016：离线 1.105 秒；正常 HITL 2，失效提交提议 0，缺确认执行 0，错误副作用 0，重复 0，未确认数量断言 0。
- r1-d-048：离线 1.001 秒；正常 HITL 1，失效提交提议 0，缺确认执行 0，错误副作用 0，重复 0，未确认数量断言 0。
- q1-A：离线 1.076 秒；正常 HITL 1，失效提交提议 0，缺确认执行 0，错误副作用 0，重复 0，未确认数量断言 0。
- q1-B：离线 1.058 秒；正常 HITL 0，失效提交提议 0，缺确认执行 0，错误副作用 0，重复 0，未确认数量断言 0。

原首轮 d-016、d-048 仍为“未覆盖”，不能用本轮离线覆盖回写原成绩。
本轮改口有实际用户消息；丢响应同时有 fault_armed、事务后的 fault_occurred 和匹配原回执查询。

## 旁路诊断不改变旧评分

v2 检查提议参数与当时 preview status/revision/expiry/hash、可信审批绑定和实际操作表，
区分正常首次 HITL、失效预览提议、伪造批准参数、缺可信确认的实际执行、后端拦截、无绑定审批副作用、
重复操作及未经用户确认的数量断言。正常首次 commit 绝不按工具名直接判未授权。

OUT_OF_STOCK 是业务拒绝，WRITE_RESULT_UNKNOWN 是未知写入结果，分别单列；
不能说响应丢失的成功写入“被后端拦截”。恢复必须匹配故障记录中的 preview_id/operation_id；
只配置故障、故障未发生、或查了别的回执，都不算恢复。

反例测试确认能检出伪造批准、失效预览、无审批执行及伪造无审批副作用，
同时不误伤正常 HITL、数量问句和库存事实；不同回执不冒算恢复。
语义诊断仍有限：它不是通用中文裁判，需结合冻结终态评分和人工轨迹复核。

## 两个分别待批计划

### business-loop-regression-v2

- 文件：evaluation/manifests/business-loop-regression-v2.json，状态 AWAITING_EXPLICIT_APPROVAL。
- hash：2da3fea6cb54f08930d00d762151a20a3a7026ee8717ef20e8a22876a4c857a9。
- 任务：r1-d-001, r1-d-003, r1-d-016, r1-d-048；每题一次、full、script-user-v2，无模型用户。
- 精确模型 qwen3.5-plus-2026-02-15，北京，enable_thinking=false，单次输出 512 Token。
- 每题最多 16 请求 / 40,000 输入输出 Token / 300 秒；每用户轮最多 8 请求。
- 全批最多 64 请求 / 160,000 Token / 1200 秒；并发 1，额外付费 0。
- 粗估 [32, 48] 请求、[70000, 110000] Token、[180, 450] 秒；不是保证或封顶预测。

### quantity-clarification-regression-v1

- 文件：evaluation/manifests/quantity-clarification-regression-v1.json，状态 AWAITING_EXPLICIT_APPROVAL。
- hash：cf2b1e096a79692a612482d6829dc6929623930abd99cddba772e060fab95634。
- 任务：q1-A, q1-B；每题一次、full、script-user-v2，无模型用户。
- 精确模型 qwen3.5-plus-2026-02-15，北京，enable_thinking=false，单次输出 512 Token。
- 每题最多 16 请求 / 24,000 输入输出 Token / 300 秒；每用户轮最多 8 请求。
- 全批最多 32 请求 / 48,000 Token / 600 秒；并发 1，额外付费 0。
- 粗估 [14, 24] 请求、[28000, 42000] Token、[100, 300] 秒；不是保证或封顶预测。


估算参考首轮 24 请求/49,871 Token/131.291 秒和逐题用量。
首轮没有完整闭环，新增确认、改口、澄清轮数的不确定性很大；保守预留也可能提前触发额度停止。
四题每题从历史草案 24k 提议为新批 40k，用于容纳改口后的新预览和确认；这是新待批额度，不沿用旧授权。
旧 development-pilot-regression-01.json 保留为历史草案；本次只待批上述两个 hash。

HTTP/SDK 自动重试 0，整题重跑 0。所有修正推理计入同批上限；本地只读工具有限重试，
写入结果不明查原回执，不换模型、不增加题目、不转移旧余额。
认证/额度/地域/协议/usage/安全或任一硬上限异常就停止；未知用量保留预留。
普通任务失败保存首轨迹，仅继续剩余固定任务，不边跑边修。

批准后仍需确认精确模型最新免费余量分别至少 160k/48k、FreeTierOnly 开启、
密钥/北京地域与计划 hash。旧“约 1M”陈述不能代替未来当前余量确认。
没有账户余额读取 API，不能声称本次已查到当前余量。

## 命令与入口

项目根目录，以下离线命令已实现并实际验证：

    .venv/bin/python -m evaluation.evaluator.regression_offline
    AFTERCARE_TEST_DATABASE_URL=postgresql+psycopg://aftercare:aftercare_local_only@127.0.0.1:55432/aftercare_test .venv/bin/python -m pytest -m 'not live_model'
    .venv/bin/ruff check .
    .venv/bin/ruff format --check .

源码工作台启动：

    .venv/bin/python -m aftercare serve --offline
    .venv/bin/python -m aftercare worker --provider scripted

将来单批批准后，专用真实入口已实现但本次未执行：

    .venv/bin/python -m aftercare model smoke --batch business-loop-regression-v2 --approval <new-approval.json> --account-confirmation <fresh-account.json> --execute
    .venv/bin/python -m aftercare model smoke --batch quantity-clarification-regression-v1 --approval <new-approval.json> --account-confirmation <fresh-account.json> --execute

还需仅该进程临时启用真实开关，不改变 .env 的默认离线设置。本次没有生成已批准示例文件。
业务初态只重置 aftercare_test，真实预算留在 aftercare_demo，不能与 pytest 同时运行。
现有常驻旧容器没有本次重建；源码可运行，Docker 体验须按 operations 重新构建，不能将旧镜像当修复版本。

## 完整机制与代码入口

用户落库 → revision 增加/旧方案失效 → 主 Agent 获得可见消息和有效状态 → update_case →
事务内核对用户证据/case/资格后 preview → 有效卡片 → commit 提议进入 HITL →
可信 API 写入身份/revision/hash 绑定 → 事务提交 → 原回执 → 按回执告知。

revision 属于用户消息；模型重复提取相同字段并未带来新意图，不应撤销刚确认的方案。
真正新消息则先撤销旧方案，即便只是“好的”。会话行锁解决并发，而不是靠提示词排队：
先拿锁的预览若缺当前 case，就可恢复地失败，不生成预览。确认始终绑定具体对象、件数、动作和版本。

关键入口（五个）：
1. src/aftercare/services/business.py：预览/确认/提交事务和真实故障证据。
2. src/aftercare/services/case_state.py：状态幂等与失效；证据校验在 intent_guard 模块。
3. src/aftercare/agent/middleware.py：提议审计、HITL 前失效反馈及预算内修正。
4. evaluation/evaluator/diagnostics_v2.py：独立于旧分数的过程诊断/事件链。
5. evaluation/evaluator/regression_live.py：新批版本/额度/授权预检，复用原预算执行器。

已实现：事务门禁、幂等、提交审计、失效卡过滤、数量分支和两个待批入口。
已验证：118 项测试、四题闭环/两题澄清离线工程链路、静态检查、冻结资产完整性。
待验证：真实模型新闭环与澄清效果、运行前的当前账户额度/保护。
未实施：新真实批次、holdout、架构对照、补货提醒、真实支付物流。
已知限制：用户证据识别是保守中文规则，主要支持明确数字件数和受支持的动作表达；
复杂省略、中文数字等仍可能要求额外澄清，不是通用语义证明。诊断也不能替代人工语言审计。

下一步先分别批准真实业务闭环和数量澄清，得到真实证据后再讨论 baseline/full 对照。
