# 项目结果总表（收尾候选）

以下均为已见开发任务或兼容检查，不是holdout/泛化成绩，不能跨版本计算效果提升。全部首次轨迹保留；原始文件索引位于evaluation/manifests/*-first-run.json和各历史报告。

| 真实批次 | 首次结果 | HTTP | 已知输入输出Token | 证据 |
|---|---|---:|---:|---|
| compatibility-smoke | 6/6兼容检查 | 6 | 1,102 | docs/experiments/compatibility-smoke.md |
| development-pilot | 0/4 | 24 | 49,871 | docs/handoffs/phase-06A-development-pilot.md |
| business-loop-regression-v2 | 2/4 | 28 | 54,787 | docs/experiments/business-loop-regression-v2-first.md（保留用户既有编辑） |
| business-loop-regression-v3 | 2/4 | 19 | 36,533 | docs/handoffs/phase-06A-business-loop-regression-v3.md |
| business-loop-regression-v4 | 4/4 | 28 | 58,590 | docs/experiments/complementary-regressions-v1.md |
| quantity-clarification-regression-v3 | 0/1已尝试，另1题未运行 | 11 | 23,437 | 同上；预算停止后未追加 |
| quantity-priority-development-v1 | 冻结3/4，数量过程3/4 | 40 | 85,600 | docs/experiments/quantity-priority-development-v1.md |
| 合计 | 分母与口径不同，不合并成功率 | 156 | 309,920 | 持久真实账本；已知未知预留0 |

原四题真实证据已取得：取消/模拟退款请求、换1件和预留、实际改口只提交新方案、实际事务后丢响应查询原operation。最近数量组03换1件和04退2件均有正确回执最终告知；07等待分支未覆盖，08先猜量被拦后澄清且无提交，但重复提议/追问。不能说“所有模型任务已稳定通过”。

当前工程验收：237 passed/0 skipped；最后固定六题的default和preview-stop替身均5/6，fa1-03“大一号”未被ScriptedModel解析，错误变体被后端拒绝；保留失败，不改题目或评分。工作台8128已更新候选源码，实际API→worker暂停烟测通过，零模型/零业务副作用。
最后真实验收仅为待批六题final-development-acceptance-v1，预算及hash见final-acceptance.md；未执行，禁止把离线结果填入真实表。

已知限制：有界中文数量/订单解析，复杂句仍需澄清；模型仍可能猜量或重复追问；case是提议而非完整事实库；脚本用户和通信评分存在措辞覆盖边界；模型草稿可能不合规，实际预览/最终通知由应用约束；普通离线ScriptedModel不具备通用理解能力；无真实支付/物流、无holdout和架构对照、无统计显著性或泛化提升结论。

收尾后仅阻断级错误（错误提交、授权绕过、重复副作用、虚假回执告知和预算安全异常）进入修复。其他问题进已知限制，不自动新一轮真实回归。任何新的真实批次仍必须独立批准，预算不继承。
