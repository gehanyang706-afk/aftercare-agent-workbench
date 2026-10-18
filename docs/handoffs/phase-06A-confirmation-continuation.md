# 6A 可信确认后的安全续跑：离线交接

工程提交 19fe7adc8ac3656bc00f238cd8a9ea7f8d99bc44。
指纹 cc773b0711a785f61001e79507555fa56779104f0cf56b49bce92844b7c9befb。
本次真实请求/Token/未知预留新增均为 0；两个新计划均未授权、未执行。
保留首轮 0/4、本轮真实 2/4 及全部原始 JSON/轨迹，不计算跨版本效果提升。
已有旧报告未提交文本插入保持原样，不纳入本次提交。

完整证据、逐题事件和计划 hash：
docs/experiments/confirmation-continuation.md/.json；
evaluation/manifests/confirmation-continuation-freeze.json。

## 已完成能力和验证

- 可信确认持久事件绑定 event_id/preview_id/用户/hash/intent_revision/decision。
- 有匹配 HITL 中断则恢复；图 END 则进入受控应用提交入口，均复用原提交工具/资格/版本/事务/幂等。
- 不伪造用户消息或增加意图版本，不从任意 CONFIRMED 行推断权限。
- 重复确认/并发恢复/重启仅一次副作用；未知结果重复事件只查原操作，不盲写。
- 预览、原始模型提议、匹配真实回执的最终告知分别记录；新输出无银行通知/真实履约建议或内部工具术语。
- 区分图已结束、等待确认、等待提交、已提交但未告知、结果未知、失败、任务完成及拒绝/接管终态。

修复前 runtime/Web 两条路径确实复现未提交；原 HITL 原本可提交，但缺统一 receipt 返回字段。
另保存无回执“退款已到账”的输出失败反例。
最终 144 passed / 0 skipped / 44.31 秒；
无网络容器 20 passed / 11.14 秒；
正常 HITL、预览后自然语言停止两模式各六题通过。
两模式的改口都实际发生，丢响应都到达事务后故障并查回同一操作，申请/预留均只有 1。
原冻结 grader.py、diagnostics_v2.py、三份场景和 script-user-v2 未改。
新诊断 process-diagnostic-v3 不把预览卡文字算提交后告知，故障配置/发生/恢复分开。

本机 http://127.0.0.1:8128 已更新为修复版 app/worker，源码 hash 已核对，真实开关 false。
重用已有本地镜像依赖层，构建网络关闭，未下载镜像/依赖/模型；演示数据库和真实账本未变。
旧镜像 aftercare-agent-workbench:before-confirmation-continuation 保留可回滚。

## 命令、数据流和机制

    .venv/bin/python -m evaluation.evaluator.regression_offline --model-mode default
    .venv/bin/python -m evaluation.evaluator.regression_offline --model-mode preview-stop
    AFTERCARE_TEST_DATABASE_URL=postgresql+psycopg://aftercare:aftercare_local_only@127.0.0.1:55432/aftercare_test .venv/bin/python -m pytest -m 'not live_model'
    .venv/bin/ruff check .
    .venv/bin/ruff format --check .

测试库使用者必须串行；不重置演示业务/真实账本。
两条最终输出目录见 runtime/confirmation-continuation/default-final.txt 与 preview-stop-final.txt。

一个完整机制：
模型结束 → 有效预览仍可展示 → 用户实际确认 → API 持久化确切批准事件并与 Job 同事务入队
→ runtime 重新校验绑定和批准 → 恢复匹配中断或应用层提交
→ 原业务服务重检资格/版本/库存/幂等 → 原操作回执 → 唯一最终告知。
graph.next 只代表调度，不代表批准、提交或业务完成。
拒绝、新消息和过期仍可阻止旧事件；已提交重复事件只回放原回执。

五个入口：
1. src/aftercare/services/confirmation.py
2. src/aftercare/agent/continuation.py
3. src/aftercare/agent/presentation.py
4. src/aftercare/workers/queue.py
5. evaluation/evaluator/diagnostics_v3.py

## 当前边界与待批计划

已实现/离线验证：两条续跑、实际工作台、并发/重启、资格变化、丢响应、状态与回执型告知。
待验证：真实模型在新修复版上的四题业务闭环及两题数量澄清。
未运行：任何新真实批次、holdout、架构对照；未接入真实支付/物流/补货通知。

business-loop-regression-v3：
四题各一次，full/script-user-v2，精确 qwen3.5-plus-2026-02-15，北京关闭思考；
每题 16 请求/40k/300 秒，全批 64 请求/160k/1200 秒。
hash b4f837fb027c7a8484303b58a7f35edb0a59075c5705c890cfc4532301256fa1。

quantity-clarification-regression-v2：
原两题各一次，同模型/配置；
每题 16 请求/32k/300 秒，全批 32 请求/64k/600 秒。
hash 112bbbaaf6c655a0db139e2355bfbf8b251d9887804ad8f6beb58533f628166f。
数量批由旧 48k 提议为新 64k 仅是待批封顶，为多轮澄清及保守预留留余量，不是旧授权或预测。

两批均并发 1、每用户轮 8 请求、单输出 512、额外付费 0、SDK/HTTP 自动重试 0、整题重跑 0。
估算以真实 v2 的 28 请求/54,787 Token/152.835 秒及离线两模式协议为参考。
B 续跑无额外模型调用，A 后续模型仍走同一账本与截止；所有异常按计划停止。
新计划必须单独批准并重核当前免费额度与 FreeTierOnly；旧 hash 明确拒绝，不转移未用预算。

限制：无完整绑定的旧队列不会自动迁移授权；保守中文规则不是完整语义证明；
A 的后续模型仍可能因预算或协议停止，不能绕开保护凑成功。
历史模型原文保留，只有新用户可见内容使用新约束。

体验：运行 preview-stop 六题，查看初始 ENDED/WAITING_CONFIRMATION 与确认后匹配回执/唯一告知；
再查看丢响应的配置、实际故障、原回执查询三条独立证据。
理解检查：为什么 CONFIRMED 状态不是执行权限？图已结束为何不能滥用 resume？
为什么操作已提交但没有最终告知时，状态仍不能写任务完成？
