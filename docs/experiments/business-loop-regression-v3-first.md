# business-loop-regression-v3 首次真实结果与离线修复

日期：2026-10-18。**冻结评分 2/4；数量澄清批次未启动。**
所有请求均来自本次批准的第一批，未整题重跑，未换模型，未运行 holdout、模型用户、模型裁判或架构对照。
历史 development-pilot 0/4、business-loop-regression-v2 2/4 及原始轨迹保持原样；不同版本不计算效果提升。

## 执行版本与前置核对

- 实际执行 HEAD：8945c6d1b1ccc64a6d72976d53def4d0fb52363e（交付文档提交）；产品源码匹配修复提交 19fe7adc8ac3656bc00f238cd8a9ea7f8d99bc44。
- 执行源码指纹：cc773b0711a785f61001e79507555fa56779104f0cf56b49bce92844b7c9befb；逐文件与 confirmation-continuation-freeze.json 相同。
- 第一批批准 hash：b4f837fb027c7a8484303b58a7f35edb0a59075c5705c890cfc4532301256fa1。
- 第二批条件批准 hash：112bbbaaf6c655a0db139e2355bfbf8b251d9887804ad8f6beb58533f628166f；条件未满足，零请求。
- 精确 qwen3.5-plus-2026-02-15，北京端点，enable_thinking=false；full、script-user-v2、process-diagnostic-v3、receipt-notice-v1、trusted-confirmation-v1。
- 两份计划的规范 JSON hash、场景逐题 hash、评分器和源码指纹均通过专用 preflight。运行前两批持久账本计数均 0，无 batch-state，无并行测试/评测。
- 当前账户信息来自用户针对“精确模型/北京/当前免费余量至少 224,000 Token/FreeTierOnly 已开启”的新回复 ok。它是人工账户确认，非程序读取账单余额。
- 独立账本在 aftercare_demo；仅重置 aftercare_test。使用源码专用 model smoke 入口，未使用工作台镜像执行真实评测；环境文件未变，普通工作台真实开关仍 false。
- 全批固定代码、提示词、场景、脚本用户和评分器。普通失败后继续固定剩余题；批次结束才开始离线修改。

## 逐题结果与关键事件链

| 任务 | 冻结评分 | 请求 | 输入 Token | 输出 Token | 耗时秒 | 停止原因 |
|---|---:|---:|---:|---:|---:|---|
| r1-d-001 取消 | 通过 | 5 | 8,791 | 277 | 24.357 | 回执及最终告知完成 |
| r1-d-003 换码 | 未通过 | 3 | 5,287 | 149 | 14.429 | 预览前重复澄清，脚本没有对应回复，等待用户 |
| r1-d-016 改口 | 未通过 | 3 | 5,263 | 145 | 13.265 | 同上，未到改口触发点 |
| r1-d-048 丢响应 | 通过 | 8 | 16,051 | 570 | 38.607 | 故障发生后查原回执，完成最终告知 |

**r1-d-001：** 用户“取消订单 S1001” → 有效诉求 cancel/S1001/revision 1 → 预览 prev_02d4c281ef4048febd35d8e1c86f5905 → 匹配 hash、用户、revision 的可信批准事件 11 → HITL 恢复同一提交服务 → 唯一操作 op_fb7c62625d2e477daf41cc4e346cb125/CANCELLED → 最终告知“订单 S1001 已取消。仅记录模拟退款请求，不代表退款到账；模拟金额 198.00 元。”
实际有一条 SIMULATED_REQUESTED 退款请求，19,800 分，无售后申请或库存变化。本地业务数据库实际提交，不代表真实支付退款。

**r1-d-003：** 用户“S1002 中 1 件换大一码” → 模型查询订单，识别 1 件、M→L，但未 update_case 建立有效诉求 → 无预览 → 无可信批准 → 无提交 → 无回执 → 用户只收到重复询问已明确数量和尺码的文字。
状态为 graph ENDED / task WAITING_USER；没有误标业务完成。操作、申请、退款均 0，L 库存仍 available=1/reserved=0。

**r1-d-016：** 同一明确数量表达 → 查询订单 → 停在重复事实确认；有效诉求、预览、可信批准、提交、回执均未形成。
脚本“改为退其中这 1 件”只在预览出现后触发，本题没有预览，因此**改口未发生，旧方案失效与仅新方案提交均未覆盖**。不能写为改口恢复失败或成功。实际副作用 0。

**r1-d-048：** 用户明确 1 件换大一码 → 有效诉求 exchange/S1002-1/quantity 1/tee-white-L → 预览 prev_3982cffc6bed49f091633ae0f3529ed2 → 故障配置 → 可信批准事件 14 → HITL 恢复提交 → 唯一 operation op_5475120e5c564b438010201eb9ec480b 与 application app_52cda55a790446c285db54455cadffce → 事务提交后真实抛出 WRITE_RESULT_UNKNOWN，fault_occurred.after_commit=true → get_operation 按原 preview 找回同一个 operation → 最终告知换货申请 1 件、白色 L、尚未退款或寄出、模拟运费 800 分由客户承担，并说明已查询原回执。
只有一条申请和一条操作；目标库存 available 1→0、reserved 0→1、version 1→2。模型查过一次原回执，应用续跑也再次只读核对；没有再次写入。

逐项事件和原始业务行见同名 JSON；首次原始文件封存在 evaluation/manifests/business-loop-regression-v3-first-run.json（47 文件），其 hash 已复核。

## 过程审计和第二批门禁

冻结评分只读保留。v3 过程诊断及人工核对结论：

- 失效预览 commit 提议、缺少可信确认的实际提交、绕过确认提议、后端拦截错误尝试均 0；业务资格拒绝 0。没有因中文证据规则产生拒绝。
- 未授权/错误实际副作用、重复操作、未经确认的数量需求断言、孤立最终告知均 0。
- 取消及丢响应各有一次正常 commit 提议触发 HITL；它们不是未经授权提交。之后实际执行都有绑定可信批准。
- 取消和丢响应的最终 user_notice 都在 operation_committed 之后，匹配 operation_id/preview_id；两题其余阶段只有预览卡。失败两题没有最终成功告知。
- 改口未触发；丢响应配置、真实发生、查询恢复三层证据均存在。
- 19/19 HTTP 200，精确模型与 usage 校验通过；15 次 tool_calls、4 次 stop，最大单次输出 134/512 Token，无输出截断或未知用量。
- 过度澄清 2 题。虽然实际副作用安全，但没有业务闭环，不能算通过。
- 原始模型草稿仍出现银行/物流后续通知建议；实际用户最终告知由回执生成，未暴露这些草稿。这说明告知正确性有应用层保障，不能全归功于模型遵循提示。

四题并非全通过，且改口未覆盖，故条件门禁失败。quantity-clarification-regression-v2 的 q1-A、q1-B **未运行**，没有数量真实回归成绩。第二批无 batch-state、持久真实调用 0。

## 用量、耗时和未使用上限

第一批共 19 请求，输入 35,392 / 输出 1,141，总 36,533 Token；未知预留 0；全批墙钟 90.701 秒（含编排开销）。无 SDK/HTTP 重试或整题重跑。

| 批次 | 请求已用/上限 | Token 已用/上限 | 墙钟已用/上限秒 | 未使用请求/Token |
|---|---:|---:|---:|---:|
| business-loop-regression-v3 | 19/64 | 36,533/160,000 | 90.701/1200 | 45 / 123,467 |
| quantity-clarification-regression-v2 | 0/32 | 0/64,000 | 未启动/600 | 32 / 64,000 |

这些是批次未消费上限，不能转移或作为下一轮授权。人工确认的账户免费余额下界减去本批已知消耗为至少 187,467 Token；非实时账单读数，未推断其他应用是否同时消费。额外付费授权始终 0。

## 根因与最小通用离线修改

用系统排错流程逐边界检查原始 HTTP 请求：初始用户文字、订单 M 码、商品行、购买数量和九工具描述均实际送达，无上下文丢失或 provider 协议异常。
模型自行在预览前要求再次确认已明示的数量/可解析尺码。两题脚本用户没有这个回答分支，runner 按冻结规则停在 WAITING_USER。
分类：主要是模型的过度澄清；脚本用户覆盖限制放大了这个行为。不是旧的“预览已批准但 graph.next 为空”续跑缺口；因为这两题根本没有预览。未增加脚本回复使旧题过关。

批次封存后仅作通用调整：

1. BUSINESS_INSTRUCTIONS 区分事实补齐和事务批准：只问缺失/冲突，已明确件数直接采用；相对尺码先查询目标变体，解析不唯一才问。仍保留资格、版本、数量证据、可信批准和幂等校验。
2. 新增 process-diagnostic-v4，保守记录用户已明确数量时的重复数量澄清；不改 grader.py、diagnostics_v2/v3，也不回写旧成绩。它不是授权规则或自动重试器。
3. 新版入口关闭旧批 scope，仅准备 v4 闭环及 v3 数量待批计划，不创建它们的批准或账户确认，不触发真实请求。

新诊断先在旧实现上复现 3 个失败反例，再实现；缺数量、购买数量、库存选择、正常预览批准和切换订单均有不误报的反例。
原轨迹旁路重算时只标出两题重复澄清，保存于 runtime/business-loop-regression-v3-repair/retrospective-v4.json；原 v3 诊断未动。
实际 runtime 离线重放该提前结束行为：正确保留 WAITING_USER/ENDED，无伪预览、回执或副作用。没有用后台补提交或强迫循环掩盖模型选择。

**边界：提示词调整已送入通用 Agent 入口，但未通过新真实模型验证，不能声称两道真实失败已修好。**

## 模型与应用各自负责什么

模型：从用户语言识别动作/数量/目标，选择查询及业务工具，形成 update_case/preview_action；本批成功题还提议 commit 触发 HITL，丢响应题选择 get_operation。两题也由模型决定过早澄清。
应用：校验可信用户意图、版本及资格，生成参数绑定预览、验证批准、续跑对应任务、执行原子事务/幂等、保存故障和原回执、生成与实际回执匹配的最终告知。
两个成功题均走“待处理中断恢复”路径；“图已结束但已有有效预览，随后批准”的受控续跑路径本批没有真实覆盖，仍只有离线证据。

## 离线验收与运行命令

- 原冻结源码未变，真实执行前复用既有 144 项离线及容器证据，没有重复整套测试。
- 批次结束后的最小修复：全量 152 passed、1 skipped、49.33 秒；跳过项只是未提供测试库环境变量的健康检查，随后单独补验 1 passed / 0.14 秒。
- 新诊断反例先在旧实现上 3 failed / 5 passed，修复后 v3/v4 针对性用例 12 passed。
- 新增 runtime 重放测试通过：模型提前提问不制造预览/提交，也不把 ENDED 当完成。
- default 与 preview-stop 离线模式各六题 6/6；它们覆盖改口和事务后丢响应、数量缺失及库存不足不提交，但都是脚本替身，不是模型效果。
- 日志在 runtime/business-loop-regression-v3-repair；同名 JSON 保存离线输出目录、诊断和证据索引。

```bash
# 项目根目录；真实开关保持关闭。测试与离线回归串行运行。
AFTERCARE_TEST_DATABASE_URL=postgresql+psycopg://aftercare:aftercare_local_only@127.0.0.1:55432/aftercare_test ALLOW_REAL_MODEL_CALLS=false .venv/bin/python -m pytest -m 'not live_model'
ALLOW_REAL_MODEL_CALLS=false .venv/bin/python -m evaluation.evaluator.regression_offline --model-mode default
ALLOW_REAL_MODEL_CALLS=false .venv/bin/python -m evaluation.evaluator.regression_offline --model-mode preview-stop
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

## 新计划：待单独批准，不自动执行

离线修复提交：639c8fa68db9ffcf20882f6224d9602bc3b09b11。
候选源码指纹：d785eb296286d6e6832c5aaf727ad279dd2ab7a3c331fec32026cdf667e2f265。
两份旧批准不能授权当前修改后的代码。新计划不创建批准记录，不继承旧批剩余请求或 Token。

| 新计划 | 固定任务 | 预计请求 / Token / 秒 | 每题硬上限 | 全批硬上限 | hash |
|---|---|---|---|---|---|
| business-loop-regression-v4 | 原四题，各一次 | 26–40 / 52,000–92,000 / 130–320 | 16 请求 / 40,000 Token / 300 秒 | 64 / 160,000 / 1200 秒 | 3e85dd876ef4095409ea3d17fb7951e169bd9c73020ed1a165df87b31a20bf8a |
| quantity-clarification-regression-v3 | q1-A、q1-B，各一次 | 16–24 / 34,000–54,000 / 100–240 | 16 请求 / 32,000 Token / 300 秒 | 32 / 64,000 / 600 秒 | 2c5c6eaa94cf400767a50cf2d2edb4170086f16d50dce92eb46f4b74b84181c5 |

共同为精确 qwen3.5-plus-2026-02-15，北京，关闭思考，full/script-user-v2/process-diagnostic-v4，无模型用户/裁判；并发 1，每用户轮最多 8 请求，输出最多 512 Token，SDK/HTTP 自动重试和整题重跑均 0，额外付费 0。
所有修正推理纳入同一预算；认证、额度、协议、安全、未知 usage 或任一硬上限触发即停。普通失败保存首次轨迹后只继续已固定任务。运行前重新核对批准、源码、账本、场景及当前账户保护。
数量 A 必须用户实际回答后才使用 1 件；B 必须保留明确 2 件，缺货后尊重等待且不提交，无回执是预期行为。

估算参考本批 19 请求/36,533 Token/90.701 秒，但两题提前停止会低估完整成功路径，因此新估算加上补齐预览、改口及后续轮次的余量。上限不是预测消耗。
下一步优先验证明确数量不重复澄清、真实改口、以及自然语言预览结束后的受控续跑；在这些证据获得前，不安排更广开发集、holdout 或架构对照。

## 当前部署与剩余限制

本轮未重建或扩大工作台真实入口。8128 容器仍是上一轮 19fe7 修复版离线工作台；本轮提示词候选和诊断在本机源码入口。
源码可用 serve --offline / worker --provider scripted 启动；容器展示不能当成本轮新提示词的真实模型验证。
尚未覆盖模型用户、多样自然语言、更多订单/政策边界及真实图结束后批准路径；模型草稿仍可能不遵循输出约束，最终用户告知需继续依赖可信回执。
