# 6A 真实业务闭环修复与回归准备交接

工程提交 41a28d4581f58dc67a0bba478b3df6020db13127；文档提交随后保存。
本次真实请求/输入输出 Token/未知预留均为 0，未运行 holdout 或架构对照。

完整报告见 ../experiments/business-loop-repair.md 和 JSON；冻结资产见
evaluation/manifests/closure-repair-freeze.json。原首轮 0/4、原题/四题回归/评分/53 份原始文件未变。

## 可用能力与验证

事务内约束有效诉求/用户证据后创建预览；相同状态幂等；新消息及字段变化撤销旧确认；
并发工具可恢复失败；失效提议在 HITL 前反馈，有效首次提议正常中断；
Web 只展示服务端仍有效的预览卡。数量未说明先问，明确 2 件且库存 1 件解释缺货并问后续选择。

最终代码上 118 passed、0 skipped、18.66 秒；四题闭环和两题数量澄清 6/6 离线通过。
9+4+4 个修复前失败日志已保存。静态检查和冻结 hash 检查通过。
改口实际触发、丢响应实际发生且按同一操作/预览查回执，仅一次副作用。
首轮 d-016/d-048 的改口/故障仍是“未覆盖”，不因本轮离线结果而重写。

运行：

    .venv/bin/python -m evaluation.evaluator.regression_offline
    AFTERCARE_TEST_DATABASE_URL=postgresql+psycopg://aftercare:aftercare_local_only@127.0.0.1:55432/aftercare_test .venv/bin/python -m pytest -m 'not live_model'
    .venv/bin/python -m aftercare serve --offline
    .venv/bin/python -m aftercare worker --provider scripted

最终离线原始输出 runtime/closure-repair/offline-20261018-002816；全量日志 runtime/closure-repair/full.txt。
已有常驻旧容器未重建，不能把旧镜像当此次修复版。

## 状态、流程和入口

已实现：门禁/幂等/审计/数量分支/待批入口。
已验证：离线工程行为和六题场景；持久真实账本仍只有旧两批。
待验证：真实模型完整闭环和数量澄清、当前账户免费额度与保护。
未执行：新真实批次、holdout、架构对照；未实现补货提醒或真实支付物流。

消息 revision → 有效 case → 原子预览校验 → 有效卡片/HITL → 可信 API 确认绑定
→ 事务提交/幂等副作用 → 原回执 → 告知。完整逐题链路在报告中。

五个入口：business.py、case_state.py、agent/middleware.py、
evaluation/evaluator/diagnostics_v2.py、evaluation/evaluator/regression_live.py。
准确路径及设计取舍见完整报告；保留九工具与原预算网关，未重构整体架构。

一个机制：用户消息才推进 revision。模型同一消息下重复写相同事实，不构成改口，
因此不撤销预览；用户真发新消息则先撤销旧预览，旧审批 hash/revision 不可再提交。
并发时共享会话行锁，不能在“检查通过”和“创建预览”之间插入新消息绕过检查。

## 待批边界与下一步

1. business-loop-regression-v2：4 题 full/脚本用户；每题 16 请求/40k Token/300 秒，
   全批 64 请求/160k Token/1200 秒。
2. quantity-clarification-regression-v1：2 题 full/脚本用户；每题 16 请求/24k Token/300 秒，
   全批 32 请求/48k Token/600 秒。

精确模型均 qwen3.5-plus-2026-02-15，并发 1、输出 512、SDK/HTTP 自动重试 0、
整题重跑 0、额外付费 0。新 hash 在各计划和冻结清单中。
计划不是授权；不得生成授权文件或调用。旧 regression-01 草案不作为本次待批版本。

运行前须获单批明确授权，核对新 hash、源码指纹、精确模型北京地域当前免费余量和 FreeTierOnly。
不把旧约 1M 陈述或旧批未用余额当新预算；异常按计划立即停止。
下一步先取得两类真实证据，再考虑成对架构对照。

已知限制：规则模型不是效果证据；保守用户证据规则不覆盖全部中文；
旁路诊断不是完整语义裁判，需结合冻结状态评分与轨迹人工复核。

可选体验：新开离线会话发“S1002 换大一码”，先不答数量，应无可确认预览；
回答“全部 2 件”后应说明库存不足并询问选择，无申请副作用。

理解检查（不阻塞交付）：为何重复状态写入不能等同新用户消息？
为何正常首次 commit 提议不算绕过批准？为何丢响应后要按原预览查回执而不是新建操作？
