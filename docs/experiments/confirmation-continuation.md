# 可信确认后的安全续跑：离线修复交付

**实现与离线验收完成；真实调用 0、真实 Token 0、未知预留新增 0。**
原首轮 0/4、本轮真实 2/4 以及两批原始文件保持原样，不回写成绩，不计算跨版本提升。
没有运行任何真实回归、数量澄清真实批次、holdout 或架构对照。

## 版本、入口和实际验证

- 修复提交：19fe7adc8ac3656bc00f238cd8a9ea7f8d99bc44。
- 源码/测试/配置指纹：cc773b0711a785f61001e79507555fa56779104f0cf56b49bce92844b7c9befb。
- 事件 trusted-confirmation-v1；告知 receipt-notice-v1；诊断 process-diagnostic-v3；脚本用户仍 script-user-v2。
- 原四题和两题数量场景文件、原 grader.py、diagnostics_v2.py 和脚本用户策略逐字未变。
- 全量离线测试 **144 passed / 0 skipped / 44.31 秒**，日志 runtime/confirmation-continuation/full.txt 和 full-junit.xml。
- 无网络容器中额外运行 **20 项续跑验收，20 passed / 11.14 秒**，日志 docker-tests.txt。
- 两种模型协议替身均各跑六题一次：原 HITL 模式 **6/6**，预览后自然语言停止模式 **6/6**。
- 原始失败保存于 before.txt：runtime 和 Web/worker 两条路径确实无副作用；既有 HITL 原本可提交，但没有统一的新回执返回字段。
  false-notice-before.txt 另保存了无回执却输出“退款已到账”的失败反例。
- ruff check/format、git diff --check、冻结 hash 检查通过；真实账本仍只有旧三批（6、24、28 请求），本次无新增。
- 旧报告 docs/experiments/business-loop-regression-v2-first.md 在开始时已有未提交文本插入，已备份并保留，未覆盖或纳入本次提交；
  权威原始 JSON、65 份真实轨迹与早期 53 份轨迹均校验未变。

完整逐题事件/回执/告知见同名 JSON；源文件和证据 hash 在 evaluation/manifests/confirmation-continuation-freeze.json。

## 修复选择：确认是持久业务事件，不是“图里有下一步”的别名

先读当前 Deep Agents/LangGraph 代码与只读 checkpoint，并复现原失败：
模型生成有效预览 → 自然语言请求确认并 finish_reason=stop → graph.next 为空
→ 可信 API 确认 → 原 runtime 直接返回旧消息，无提交。

本次保留单主 Agent、九工具、原提交服务和 PostgreSQL，不改成另一套 Agent 架构：
1. 确认事务持久化事件并返回 event_id、preview_id、principal、parameter_hash、intent_revision、decision。
   工作台在同一确认事务里把该绑定放入 Job.result，评测进程只转发真实 API 确认返回值；不传答案或隐藏目标。
2. runtime 先检查事件、所属会话/用户、原预览参数 hash、用户意图版本、审批记录和当前有效性。
   不能只看到 CONFIRMED 就选择一个方案；绑定缺失/伪造/改口后过期都拒绝。
3. **有匹配中断**：只允许恢复该绑定对应的单个 commit_action 中断，保持原 HITL 路径。
4. **图已经结束**：不假装 Command(resume) 能启动新图，进入应用层受控续跑，调用同一个 commit 工具和 BusinessService.commit。
   这是明确“确认并提交”事件驱动的条件执行，仍检查全部批准与资格；不是无条件自动提交。
5. 同一会话用 PostgreSQL session advisory lock 串行化 runtime；底层仍按原幂等键、锁和事务保证唯一副作用。
   已提交重复事件只查原回执；执行结果未知时，后续恢复也只查原操作，不盲目再写。
6. 内部续跑不追加 HumanMessage，不增加 intent revision。后续确需模型时仍由原模型、BudgetLedger、计数和硬截止执行；
   图结束后的应用续跑本身不增加模型请求。
7. 新用户可见最终告知由真实回执、原批准数量和政策报价构造，按 operation 去重保存；
   预览告知、模型原始提议和提交后告知分别记录。不能将旧问题原样返回并标成完成。

实际工作台与评测调用的是同一个 run_turn/confirmation continuation；不是在评分脚本里补提交。

## 状态定义

| 状态 | 判断依据 |
|---|---|
| WAITING_CONFIRMATION | 存在本轮有效 PENDING 预览；可确认，尚未提交 |
| graph_state=ENDED | 图本轮已经结束，只说明调度状态，不说明业务完成 |
| WAITING_SUBMISSION | 实际可信批准已落库，等待处理该事件 |
| SUBMITTED | 已有实际操作回执，但匹配最终告知尚未持久化 |
| EXECUTION_UNKNOWN | 写入结果未定；只查询原操作，不能报成功或盲目重写 |
| FAILED | 执行/资格失败，或遗留 COMPLETED 字样却没有实际回执 |
| COMPLETED | 对应实际操作回执与匹配最终告知都存在 |
| REJECTED / HANDOFF_PENDING | 合法拒绝或人工接管终态，分别与相应业务记录绑定 |
| WAITING_USER | 仍需澄清或用户选择暂不提交，不能称为业务完成 |

Job 状态不再因为执行片段正常返回就一律 COMPLETED；图结束、等待确认、结果未知和任务失败单独处理。
前端显示业务任务状态，普通模式不展开原始工程审计 JSON；开发演示模式仍可查看原始记录。
重复事件和重启后的回执回放不新增用户意图版本，也不产生第二条最终告知消息。

## 有意义的验收覆盖

| 要求 | 实际测试证据 |
|---|---|
| 预览后自然语言停止，确认后完成一次提交与最终回执 | test_ended_graph_confirmation_produces_receipt_not_old_question；preview-stop 六题 |
| 原 HITL、取消和改口保持正常 | test_existing_hitl_path_still_submits_once；原有 agent/e2e 套件；default 六题 |
| 拒绝确认不提交 | runtime 拒绝测试及实际 API→worker 拒绝测试 |
| 改口后旧批准不提交旧方案 | test_old_approval_event_after_new_intent_cannot_commit |
| 重复确认、并发恢复、进程重启唯一副作用 | 双线程恢复、重建 graph/checkpointer、实际过期 worker lease 回收/重复确认；只有 1 operation/application/reservation |
| 订单/库存/政策变化重新校验 | 三种参数化测试，拒绝并作废旧方案，没有申请副作用 |
| 事务后丢响应查原 operation | 两种协议模式均真实注入本地事务后故障，匹配原 preview_id/operation_id，只有一次申请/库存变化 |
| 无节点不能返回旧问题冒充完成 | 初始 ENDED/WAITING_CONFIRMATION、确认后 fresh final notice、无回执 legacy COMPLETED 反例 |
| 工作台与评测一致 | 实际 API、实际 worker 子进程及无网络容器 20 项验收；预算化真实协议替身也验证 B 路径不新增模型请求 |
| 未知写入重复恢复不再盲写 | test_unknown_result_duplicate_event_only_queries_does_not_write_again |
| 预览文本不冒充最终告知 | v3 诊断反例：缺失/错配/早于提交的 final notice 均不能算完成 |

## 四题和两题数量澄清的离线事件链

下表两种模式均验证；实际逐题参数、回执和事件 ID 见 JSON。
不是新真实模型分数，也不与历史 0/4、2/4 计算提升。

| 任务 | 用户表达 → 有效诉求 → 预览 → 可信确认 → 提交 → 回执 → 告知 |
|---|---|
| r1-d-001 | 取消 S1001 → cancel/S1001 → 整单预览 → 事件绑定批准 → 唯一取消及模拟退款请求 → CANCELLED → 仅模拟、不代表到账，无银行通知建议 |
| r1-d-003 | 换 1 件大一码 → exchange/1 → 白色 L/1 → 事件绑定批准 → 唯一申请/库存预留 1 → EXCHANGE_REQUESTED → 实际数量、目标和模拟运费告知 |
| r1-d-016 | 换 1 件预览 → 用户实际改为退这 1 件 → 旧方案失效/revision 2 → 新退货预览和批准 → 仅新方案提交 → RETURN_REQUESTED → 新回执告知 |
| r1-d-048 | 换 1 件预览 → 故障已配置 → 批准 → 实际事务提交 → 真实丢响应 → 按原预览查同一 operation → 最终告知；申请/预留各 1 |
| q1-A | 未说数量 → 先问件数，无有效预览 → 用户实际答“其中 1 件” → quantity 1 → 预览/批准/唯一提交 → 回执及最终告知 |
| q1-B | 未说数量 → 问件数 → 用户答“全部 2 件” → 保留 quantity 2、库存不足无有效预览 → 问后续选择 → 用户暂不提交 → 无操作/申请/库存预留，不改 1 件或退货 |


### default 协议模式

- r1-d-001：通过；脚本模型调用 5 次，耗时 1.98 秒；副作用 {'operations': 1, 'applications': 0, 'refunds': 1}；匹配回执与最终告知 True；故障发生 False、恢复 False。
- r1-d-003：通过；脚本模型调用 6 次，耗时 2.018 秒；副作用 {'operations': 1, 'applications': 1, 'refunds': 0}；匹配回执与最终告知 True；故障发生 False、恢复 False。
- r1-d-016：通过；脚本模型调用 10 次，耗时 2.202 秒；副作用 {'operations': 1, 'applications': 1, 'refunds': 0}；匹配回执与最终告知 True；故障发生 False、恢复 False。
- r1-d-048：通过；脚本模型调用 7 次，耗时 1.979 秒；副作用 {'operations': 1, 'applications': 1, 'refunds': 0}；匹配回执与最终告知 True；故障发生 True、恢复 True。
- q1-A：通过；脚本模型调用 9 次，耗时 2.118 秒；副作用 {'operations': 1, 'applications': 1, 'refunds': 0}；匹配回执与最终告知 True；故障发生 False、恢复 False。
- q1-B：通过；脚本模型调用 10 次，耗时 2.072 秒；副作用 {'operations': 0, 'applications': 0, 'refunds': 0}；匹配回执与最终告知 False；故障发生 False、恢复 False。

### preview-stop 协议模式

- r1-d-001：通过；脚本模型调用 4 次，耗时 1.889 秒；副作用 {'operations': 1, 'applications': 0, 'refunds': 1}；匹配回执与最终告知 True；故障发生 False、恢复 False。
- r1-d-003：通过；脚本模型调用 5 次，耗时 1.862 秒；副作用 {'operations': 1, 'applications': 1, 'refunds': 0}；匹配回执与最终告知 True；故障发生 False、恢复 False。
- r1-d-016：通过；脚本模型调用 9 次，耗时 2.122 秒；副作用 {'operations': 1, 'applications': 1, 'refunds': 0}；匹配回执与最终告知 True；故障发生 False、恢复 False。
- r1-d-048：通过；脚本模型调用 5 次，耗时 1.851 秒；副作用 {'operations': 1, 'applications': 1, 'refunds': 0}；匹配回执与最终告知 True；故障发生 True、恢复 True。
- q1-A：通过；脚本模型调用 8 次，耗时 2.1 秒；副作用 {'operations': 1, 'applications': 1, 'refunds': 0}；匹配回执与最终告知 True；故障发生 False、恢复 False。
- q1-B：通过；脚本模型调用 10 次，耗时 2.049 秒；副作用 {'operations': 0, 'applications': 0, 'refunds': 0}；匹配回执与最终告知 False；故障发生 False、恢复 False。

q1-B 不产生操作，其 receipt_and_notice_complete 为 false 是预期的等待/不提交状态，不是伪造成功回执。
两组改口均有真实脚本用户消息，丢响应均有 fault_occurred 与匹配原回执查询；只有故障配置不算覆盖。

## 通用告知和版本化诊断

模型原文作为 model_text_proposal 留在审计中；新用户可见内容是 user_notice。
预览阶段明确“尚未提交”；最终阶段必须有 operation_id/preview_id 匹配且晚于 operation_committed 的告知。
不从模型 finish_reason 或旧图消息推断完成。诊断反例覆盖错 operation、错 preview、先于提交和只有预览卡文字。
故障配置（评测 fault_armed 或工作台 demo_fault_injected）、实际 fault_occurred、原回执恢复分别输出。

回执型告知由业务真实字段生成；不会建议等待不存在的银行通知、物流或履约。
无回执的“退款已到账”等提议被通用输出约束阻止；普通用户不会收到可信 API、commit_action 等内部术语。
没有按任务 ID 特判，没有修改冻结评分器或将历史模型原文清洗回写。

## 实际离线工作台和回滚

已使用本地原有 aftercare-agent-workbench:local 依赖层叠加新源码，构建网络关闭，没有下载镜像/依赖/模型。
新版 app/worker 已运行在 http://127.0.0.1:8128 ，源码 hash 与本次提交一致，真实开关仍 false。
更新前后演示订单、订单行、库存和真实预算账本 hash/计数均未变化，数据库没有重建。
数据库只在离线验收时重置独立 aftercare_test，不重置 aftercare_demo。
镜像 ID 和逐文件对照在 JSON deployment 节。

镜像回滚（仅本项目 app/worker，仍不改数据库）：

    docker tag aftercare-agent-workbench:before-confirmation-continuation aftercare-agent-workbench:local
    AFTERCARE_PORT=8128 docker compose --profile app up -d --no-deps --no-build app worker

该探针仍保留历史 phase-4-infrastructure 标签，它仅代表基础设施就绪；
本次版本依据镜像 ID 与容器源码 hash 核对，不能仅凭探针标签判版本。

## 可运行命令

项目根目录：

    .venv/bin/python -m evaluation.evaluator.regression_offline --model-mode default
    .venv/bin/python -m evaluation.evaluator.regression_offline --model-mode preview-stop
    AFTERCARE_TEST_DATABASE_URL=postgresql+psycopg://aftercare:aftercare_local_only@127.0.0.1:55432/aftercare_test .venv/bin/python -m pytest -m 'not live_model'
    .venv/bin/ruff check .
    .venv/bin/ruff format --check .

测试、离线评测和容器验收必须串行使用测试库。两种模式只验证工程协议，不支持真实模型参数。
部署脚本 Dockerfile.offline-update 依赖已有项目镜像；没有本地旧镜像时不隐式下载，
应先按 operations 的依赖安装/构建流程确认资源。

## 两个新版待批计划

### business-loop-regression-v3

- 文件 evaluation/manifests/business-loop-regression-v3.json，**未授权、未执行**。
- hash：b4f837fb027c7a8484303b58a7f35edb0a59075c5705c890cfc4532301256fa1。
- 精确模型 qwen3.5-plus-2026-02-15，北京，关闭思考，full，script-user-v2，无模型用户。
- 任务 r1-d-001, r1-d-003, r1-d-016, r1-d-048，各一次；每题最多 16 请求 / 40,000 Token / 300 秒。
- 全批最多 64 请求 / 160,000 输入输出 Token / 1200 秒；每用户轮 8 请求，单次输出 512，并发 1。
- 粗估 [24, 36] 次请求、[48000, 80000] Token、[120, 300] 秒，非保证；上限不是预计消耗。
- Business limits unchanged from previous 160k/64 scope, but NO old permission transfers.

### quantity-clarification-regression-v2

- 文件 evaluation/manifests/quantity-clarification-regression-v2.json，**未授权、未执行**。
- hash：112bbbaaf6c655a0db139e2355bfbf8b251d9887804ad8f6beb58533f628166f。
- 精确模型 qwen3.5-plus-2026-02-15，北京，关闭思考，full，script-user-v2，无模型用户。
- 任务 q1-A, q1-B，各一次；每题最多 16 请求 / 32,000 Token / 300 秒。
- 全批最多 32 请求 / 64,000 输入输出 Token / 600 秒；每用户轮 8 请求，单次输出 512，并发 1。
- 粗估 [16, 24] 次请求、[32000, 52000] Token、[100, 240] 秒，非保证；上限不是预计消耗。
- New pending quantity plan raises per-task ceiling 24k -> 32k and batch 48k -> 64k for 2-3 user turns and conservative reservation headroom. These are proposed ceilings requiring new approval; tasks/request ceilings are unchanged.


估算参考真实 v2 的 28 请求/54,787 Token/152.835 秒，及新离线协议调用数。
B 路径在确认后不需额外模型推理；A 保持原图路径，所有后续推理仍计入同批预算。
输出告知由应用渲染，不额外调用模型用户或模型裁判。
数量两题有多轮澄清，32k/题为保守预留留出余量；这是新待批上限，不能当成旧授权或预测支出。

两批额外付费授权均为 0，SDK/HTTP 自动重试 0，整题重跑 0；
未知 usage、认证/额度/地域/协议/安全或任一硬上限异常立即停止并保留预留；
普通任务失败保留首次轨迹，仅继续剩余固定任务，不边跑边改。
所有请求和修正推理都受原账本/请求计数/截止约束，不换模型、不扩题、不转移旧剩余额度。
必须分别明确批准新 hash，并在将来运行前重新确认当前免费余量和 FreeTierOnly；
本次没有生成新审批文件，也没有启动真实入口。
旧 business-loop-regression-v2 已结案；旧 quantity-clarification-regression-v1 已过期，
入口明确拒绝旧计划/旧 hash。

## 五个核心入口与一个完整机制

1. services/confirmation.py：从真实事件核验用户、对象、hash、revision 与批准记录。
2. agent/continuation.py：匹配中断恢复、图结束应用续跑、原回执查询。
3. agent/presentation.py：回执型最终告知、阶段与消息去重、状态记录。
4. workers/queue.py：在可信确认事务内持久化绑定，由实际 worker 带入 runtime。
5. evaluator/diagnostics_v3.py：区分预览、模型提议、最终告知及三层故障证据。

完整机制：模型已经结束并不取消用户看见的有效预览。用户点击确认后，
应用保存“批准哪一个确切方案”的事件。runtime 重新验证它：
有匹配中断就恢复该中断；没有中断就对这个被批准的方案调用原提交服务。
该服务再次检查资格、版本、库存和幂等；成功后按原操作回执发出且只保存一次最终告知。
重复确认只会重放同一个操作；新用户消息推进 revision 后，旧批准事件不再能执行。
因此无需伪造一句“用户再次说继续”，也不用靠模型按固定顺序调用工具来保证提交。

## 状态边界和已知限制

- 已实现并离线验证：两条确认路径、真实工作台、拒绝/改口、并发/重启幂等、资格变化、
  事务后丢响应、完成/告知诊断和无网络镜像验收。
- 待验证：真实模型在新修复版下的闭环和数量澄清；新计划未批准。
- 未运行：新真实批次、holdout、架构对照；未实现真实支付、物流或补货提醒。
- 旧队列若缺少完整绑定事件会安全拒绝，不能从 CONFIRMED 字样反推权限；
  需要以新消息/新预览重新确认，不会自动迁移旧授权。
- A 路径仍可能消耗模型预算；触发预算/协议/截止异常时照常停止，不能为凑成功放宽上限。
- 保守中文证据规则及语言诊断仍非完整语义裁判；保留终态检查和人工复核。
- 所有历史 raw/成绩不回写；本轮离线结果不代表真实模型成功率或效果提升。

下一步只等待新版真实回归计划的单独批准，不自动执行任何批次。
