# 数量处理优先批次：离线准备与冻结交接

2026-10-18。本轮真实请求/Token/新增未知预留均为0；不运行原四题真实重跑、holdout、模型用户或架构对照。
已接受的业务闭环4/4、数量q1-A失败/q1-B未运行及更早成绩、轨迹均保留。

## 可直接审批的新计划

文件：evaluation/manifests/quantity-priority-development-v1.json。
Hash：0eabc9b920ca86a8bfa920bb7dc81a20278f0829299c4857bf0e8324f9ede32b。
执行源码提交：fa8d066012effe8e3e37ad45a0dfe282832ecadc。
源码指纹：ca9790ad6094e314cb36f1d5dd03b02f8960d6718d10e0901b026a9ea0c1ac75。
状态：待单独批准，未创建批准/账户确认，未运行。旧八题hash已被新scope取代。

| 顺序/来源 | 核心任务 | 请求/Token/秒硬上限 | 预计请求/Token/秒 |
|---|---|---|---|
| qp1-03 ← dv1-03 | 换货未说数量，实际回答“其中一件”后办理 | 16 / 48,000 / 300 | 11–14 / 26k–35k / 55–100 |
| qp1-04 ← dv1-04 | 退货未说数量，实际回答“全部两件”后办理 | 16 / 40,000 / 300 | 7–11 / 16k–27k / 35–80 |
| qp1-07 ← dv1-07 | 明确两件换货，缺货后保留两件暂不提交 | 16 / 40,000 / 300 | 7–11 / 15k–26k / 35–80 |
| qp1-08 ← dv1-08 | 未说数量→澄清两件→缺货→暂不提交 | 16 / 48,000 / 300 | 11–15 / 24k–38k / 55–110 |

全批硬上限64请求/176,000输入输出Token/1200秒；预计36–51请求/81k–126k/180–370秒。
同一精确qwen3.5-plus-2026-02-15、北京、关闭思考、full、script-user-v2、process-diagnostic-v5；并发1，每用户轮8请求，输出512，自动重试/整题重跑0，额外付费0。
顺序用于逐层观察数量→退货→缺货→组合路径，各题独立初态。普通失败保存第一次轨迹后继续；不设业务成功率门禁。
认证、额度、协议、安全、未知usage或任一硬上限停止所有后续真实请求；只重置aftercare_test，真实预算账本始终保留。

预算依据：旧q1-A已用23,437，下一完整预留9,062，合计32,499。48k为澄清换货和三轮组合留出额外余量；较短退货/明确缺货用40k。
字节预留公式未降低；区间是估计，模型推理变长仍可能提前停止。每题cap持久绑定其账本会话，重启/子进程均复用，不能借用其他题48k或剩余额度。
执行前仍需该hash的新批准，以及精确模型当前免费余量至少176k、北京及FreeTierOnly确认。旧余额记录不作为当前余额。

## 离线修改与验收

- quantity-evidence-v2支持一至十、两及阿拉伯数字件数；“其中一件/全部两件/另一件保留”有界识别，不从购买数/库存推算。
- 同订单只改动作、未撤回数量时，沿用先前明确件数；否定原选择、换订单、数量冲突/备选/不确定及不同对象时清空证据、保留澄清。未支持的复杂表达不强行解释。
- 新四题单独版本化为evaluation/dev/quantity-priority-v1.jsonl，实际回复用中文件数，原dv1文件及其他历史场景/断言不改。其余dv1-01/02/05/06保留后续开发，不纳入本批。
- process-diagnostic-v5在执行前记录quantity-bearing update_case/preview_action参数及用户证据，区分无证据提议、后端拦截、澄清恢复、最终副作用/不提交、回执告知及模型停止。
- 回执收尾不依赖模型最后一句成功。已提交时已知预算/协议/认证/usage/安全/截止停止只读原回执完成告知，原停止码仍使评测失败并停批次；未知预留和暂停状态不清零。无匹配回执不能补提交或伪造成功。
- 同一可信事件的重复回放保留STOPPED和原停止码，无新增副作用；实际工作台worker与评测入口共用runtime。8128旧离线镜像本轮未重建，源码已更新，普通真实入口未开放。

最终全量223 passed/0 skipped/56.15秒；正常与图结束两种离线模式的新四题各4/4；否定/跨轮单位验收46项。
专门反例证明：先猜数量被拦，后来澄清并成功提交/告知，quantity_process_clean仍false；业务完成、冻结评分和过程缺陷独立报告。
初始兼容性失败及停止码缺口均先保存失败证据后修复，日志runtime/quantity-priority-preparation；没有修改旧测试预期来回避同订单数量继承问题。
新四题离线中03/04回执告知齐全，07/08无operation/application/库存预留，no_submit_honored=true；不提交时receipt字段为不适用，不能强行办理凑闭环。

## 命令与机制

```bash
# 项目根目录，全部离线；串行执行
AFTERCARE_TEST_DATABASE_URL=postgresql+psycopg://aftercare:aftercare_local_only@127.0.0.1:55432/aftercare_test ALLOW_REAL_MODEL_CALLS=false .venv/bin/python -m pytest -m 'not live_model'
ALLOW_REAL_MODEL_CALLS=false .venv/bin/python -m evaluation.evaluator.regression_offline --scenario-file evaluation/dev/quantity-priority-v1.jsonl --model-mode default
ALLOW_REAL_MODEL_CALLS=false .venv/bin/python -m evaluation.evaluator.regression_offline --scenario-file evaluation/dev/quantity-priority-v1.jsonl --model-mode preview-stop
```

完整机制：用户实际消息→带来源的数量证据→模型参数独立审计→后端预览资格校验→可信批准绑定→原子提交/幂等→按原回执告知；错误提议即使恢复也不删除。
五个入口：services/quantity_evidence.py、services/intent_guard.py、agent/middleware.py、agent/continuation.py、llm/regression_scope.py（均在src/aftercare/）；诊断在evaluation/evaluator/diagnostics_v5.py。
自检：为什么购买两件不等于申请两件？为什么业务完成后评测仍可失败？为什么40k题不能借另一题48k？证据分别在用户消息来源、execution_stop和账本会话预算绑定。
冻结与证据索引：evaluation/manifests/quantity-priority-freeze-v1.json。
