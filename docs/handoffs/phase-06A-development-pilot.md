# 阶段 6A：development-pilot 首轮结案

**批次执行完成，但任务成功 0/4；没有真实业务闭环通过。**
执行代码 6c547ef，精确模型 qwen3.5-plus-2026-02-15，full，脚本用户，原四题各一次。
计划 hash 9eb8329777e719103f86c188bea0d99d84ec4a9250f2a31575e2a76fd810d894。
全部首次结果/问题归类/逐题用量见 docs/experiments/development-pilot-first.md / .json。

## 命令与实际结果

本轮已经执行，禁止直接重跑同一批次：

```bash
ALLOW_REAL_MODEL_CALLS=true .venv/bin/python -m aftercare model smoke \
  --batch development-pilot --approval runtime/development-pilot-preflight/approval.json \
  --account-confirmation runtime/development-pilot-preflight/account-confirmation.json --execute
```

退出码 0 表示获批四题全部尝试完毕，**不表示任务通过**；逐题 success 全为 false。
实际 24 次 HTTP、无重试，输入 48,040 / 输出 1,831，总 49,871 Token，未知预留 0，批次 131.291 秒。
每题 4/6/7/7 请求，分别 6,551/11,751/15,766/15,803 Token，均未触上限。
账本 24 条全部 SETTLED、总量一致、剩余预留 0。没有授权/额度/协议/usage/超时异常。
原始轨迹 53 个 JSON 文件的 hash 已冻结在 evaluation/manifests/development-pilot-first-run.json。
未追加任务、未运行模型用户、未读 holdout、未做正式对照。默认真实开关仍 false，旧批持久状态拒绝复跑。

发送前离线 74 passed、0 skipped、30.13s，offline-tests.log / offline-junit.xml。
包含九工具真实协议转换、持续确认、中途改口、业务丢响应恢复、未知用量/请求数/预算边界与消息配对。
业务测试库重置前后，持久库 32 条调用记录完全相同；证据 development-pilot-preflight.json。
本机工作台容器仍使用阶段 5 离线脚本镜像，真实适配只注入获批评测入口，不全局开启。

## 数据流与机制

冻结计划/审批/账户确认 → 专用 runner → aftercare_test 初态 → 仅当前消息进入 Deep Agents →
九工具双白名单/当前有效状态 → 同一 BailianAdapter 与单次 HTTPS 传输 → 持久 BudgetLedger →
真实工具/预览/HITL → evaluator 可信确认（仅有效卡）→ 业务事务/唯一回执 → 独立原始行评分。

真实调用账本在 aftercare_demo 的独立 ledger_conversation，业务会话在 aftercare_test；明确映射保存。
每题只重置业务 fixture，真实预留、请求数和结算不清零。每请求硬截止与每题/全批截止同时有效。
独立用户/答案不进入模型；产品只见原消息、受控状态和工具结果，没有场景 ID、未来脚本或故障答案。

“安全阻止不等于任务成功”：第一题模型先预览再更新诉求，造成自己的预览失效，随后提议提交旧方案。
HITL 阻止实际执行，没有错误退款，但应办的取消也没有完成，必须计失败。
其余三题输入未指定数量，模型按购买量 2 件申请、库存只剩 1，正确拒绝后脚本用户无数量回复。
不是数据库故障；也不能把这些样本简单归为模型不懂业务。改口和丢响应阶段根本没有触发。

五个入口：llm/real.py；llm/pilot_gateway.py；agent/context.py / middleware.py；
evaluation/evaluator/pilot.py；evaluation/evaluator/pilot_actor.py。

## 工程问题、修复与边界

发送前完整轨迹保守预留超限，优化通用上下文而非预算：保留有效事实/原始近期用户消息、
完整预览调用块与提交回执，可信预览替代重复读轨迹；原 checkpoint/审计不改写，不调用摘要模型。
发送期间未改代码、配置、场景、评分或用户策略。

首轮之后只做离线通用修复：preview_action 需当前 update_case 完成，否则 CASE_UPDATE_REQUIRED；
注入可信业务时间，提示数量应澄清。业务资格、库存、确认和幂等规则未改。
修复后不重新使用本批剩余 Token，没有任何新的真实回归。
离线修复后全量 **75 passed、0 skipped、31.19s**，post-fix-tests.log / post-fix-junit.xml；
具体源文件 hash 与测试计数见 development-pilot-offline-fix.json。
离线协议测试使用明确模拟 usage；预算边界单独测试，字节/4 模拟不是生产计费预测。
原模拟计费导致的预算失败日志保留，不能把调整测试 double 当作真实用量改善。

数量明确化的四个候选另存 regression-v1.jsonl，并有数据版本说明；原 scenarios.jsonl 和评分器保持不变。
后续新题是已见开发回归，不能换名冒充盲测，也不能混入首次 0/4 成绩。

## 四种状态与下一步

已实现：受限真实模型适配、九工具、可信确认/事务代码、持久预算、专用四题 runner。
已验证：离线协议/事务链路；真实模型接口与六类工具执行；24 请求的预算/usage 完整性。
未验证：真实确认提交闭环、改口实际恢复、丢响应实际恢复、长期语言质量/稳定性。
未执行/未授权：修复后的真实回归、正式成对对照、holdout、模型用户或额外批次。

补充安全审计：实际操作/退款/重复操作均 0；业务提交层无未授权写执行，但存在一次失效预览提交提议。
冻结过程评分虽通过，不能据此称无模型行为缺陷。有 3 次未经确认的数量归因，无虚假到账/寄出成功告知。

下一批草案 development-pilot-regression-01.json：明确其中 1 件，4 题各一次，full/脚本用户，
每题 24k/16 请求、全批 96k/64 请求、20 分钟、并发 1、额外付费 0；必须独立批准。
先拿到取消/换码/改口/恢复各一条真实闭环证据，再冻结同用户策略与预算，考虑 react-full-policy/full 成对对照。
当前不应拿未覆盖的恢复阶段或 0/4 结果得出架构优劣。

体验任务：沿 d-001 的四个 request_id 找到预览从 PENDING 到 INVALIDATED，并确认根本没有操作回执。
三个问题：被拦住为何仍失败？数量歧义应由模型、用户策略还是数据负责？故障未触发为何不能称恢复失败？
