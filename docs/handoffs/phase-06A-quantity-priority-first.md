# 数量优先首次真实批次及离线暂停修复交接

2026-10-19。真实批次已结束，不再调用模型。冻结评分3/4，数量过程干净3/4，不是四题全面通过。逐题证据、事件链、请求/Token/停止状态、词面误拒绝和模型草稿缺陷见docs/experiments/quantity-priority-development-v1.md及同名JSON。

执行产品fa8d066，源码ca9790…1ac75；计划0eabc9…ede32b。独立账本40请求、输入82,900/输出2,700、未知预留0、192.414秒，无未运行项。03唯一换1件且L预留1，图结束续跑；04唯一退2件，无退款/库存副作用，HITL恢复。两题最终告知均依据实际回执。
07冻结脚本没识别“库存只有1件/需求2件”，用户等待分支未投递，保留失败；08无证据update_case与preview_action(quantity2)均记录，拦截后用户明确两件，缺货后实际选择暂不提交，无业务副作用，但又提议预览并重复追问。不能用终态无提交隐藏模型过程缺陷。

## 批后离线修改

按systematic-debugging先保留失败复现，不改指令或评分。通用run_turn在当前真实用户消息明确暂停时，核对身份/消息/revision，直接保存暂停告知PAUSED_BY_USER；graph_state=NOT_INVOKED仅表示本轮未进入图，不伪称清理了旧checkpoint。旧预览已由append_message失效，后续真正新诉求仍走原恢复规则。
暂停不调用模型、不产生operation/application/reservation，不改变数量证据或用户revision，不撤销先前申请，不安排补货自动办理；重复消息幂等保存notice。旧暂停事件不能盖掉新诉求，条件/否定/跨订单混合语句不硬判。API→worker与评测共用runtime，前端显示明确暂停状态。
script-user-v3-candidate只离线验证明确数值缺口的问句，未接入runner；v2、grader、v2—v5诊断、历史场景及成绩保持。scope单测移除“本机必然没有运行过该批”的状态依赖，使用临时目录，并另测源码变化拒绝合法旧批准；不降低生产门禁。

## 验证及复用

本次执行前复用未变源码的223项离线验收。批后新修复先有失败复现，目标验证9项通过；实际API停跑、已有HITL图暂停、重复消息、旧消息拒绝及已有提交不撤销均有行为测试。
后续最终全量和两种协议回归证据写入批后freeze及本文件补充。原真实运行封存在quantity-priority-development-v1-first-run.json，不因离线修复改为通过。

```bash
# 全部离线，串行执行；禁止与真实评测并行。
AFTERCARE_TEST_DATABASE_URL=postgresql+psycopg://aftercare:aftercare_local_only@127.0.0.1:55432/aftercare_test ALLOW_REAL_MODEL_CALLS=false .venv/bin/python -m pytest -m 'not live_model'
ALLOW_REAL_MODEL_CALLS=false .venv/bin/python -m evaluation.evaluator.regression_offline --scenario-file evaluation/dev/quantity-priority-v1.jsonl --model-mode default
ALLOW_REAL_MODEL_CALLS=false .venv/bin/python -m evaluation.evaluator.regression_offline --scenario-file evaluation/dev/quantity-priority-v1.jsonl --model-mode preview-stop
```

## 一个完整机制及入口

当前用户明确“暂不提交”→append_message增加一次真实用户revision并失效旧预览→共享runtime核对消息身份/新旧版本→有界识别无条件暂停→跳过模型图、保存幂等暂停notice和状态→API/worker/评测均可观察，不伪造回执或任务COMPLETED。以前已提交的申请不撤销，仍可按原operation查询。
入口：src/aftercare/services/user_pause.py、agent/runtime.py、agent/presentation.py、evaluation/evaluator/user_policy_v3.py、tests/agent_contract/test_user_pause.py。

已验证：03/04真实申请和回执、两种确认路径；08安全拦截和最终无提交。未验证：07实际等待选择、无证据模型数量提议彻底消失、新暂停实现的真实模型表现。新测试不能证明模型能力改善。
下一步优先新表达开发覆盖，保留dv1-01/02/05/06；增加缺货数值措辞及条件/否定暂停，独立观察澄清恢复与有效预览、不提交与清晰告知。另冻源码/策略/预算，重新审批，不能沿用旧hash、旧批剩余额度或直接重跑原题。
自检问题：为什么08评分通过但过程不干净？为什么07无副作用仍未覆盖等待？为什么NOT_INVOKED不等于业务提交成功？分别查看无证据提议、脚本实际投递事件和回执绑定最终告知。
普通工作台真实入口未扩大；8128旧离线镜像未重建。没有holdout、模型用户/裁判、架构对照。用户原有business-loop-regression-v2-first.md修改保持不动。

## 最终离线验证与修复版本

修复提交dbd44ae27403209c89fbc40442a7e44d090a519d；源码指纹7a4a1ef7d664d19a7030ad4dd733f622e971680e41e23481de5e76ddb8a11316。全量235 passed / 0 skipped / 70.80秒；两种协议替身default、preview-stop的新四题各4/4，07/08最后均为PAUSED_BY_USER / NOT_INVOKED，无新增模型或业务副作用。ruff检查、格式及diff检查通过。
首次全量2 failed / 231 passed / 1 skipped源于过时scope单测和未显式设置健康检查测试URL；日志保留，修正测试隔离及环境后全量通过，未修改生产授权门禁或评分。
证据与源码逐文件冻结：evaluation/manifests/quantity-priority-postrun-repair-v1.json。真实账本最终仍40请求/85,600 Token，reserved0/paused=false；历史非离线合计156请求/309,920 Token。本批首次95份哈希复核未变，用户既有报告编辑哈希未变。新修复未进行真实验证，没有可直接续跑的新授权。
