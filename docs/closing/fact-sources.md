# 事实来源核对与最后必要修复

本轮仅离线，0真实模型请求，未改BUSINESS_INSTRUCTIONS、冻结评分器、v2—v5历史诊断及历史场景成绩。

| 内容 | 实际权威来源 | 核对结论 |
|---|---|---|
| 客户身份 | 服务端会话与BusinessService principal | 模型不能指定身份或批准状态 |
| 购买数、订单状态、占用量 | get_order / PostgreSQL订单行 | 购买2件不等于申请2件；原始工具结果与模型参数分别保留 |
| 库存 | get_inventory及提交事务行锁重检 | 库存1件不能反推申请量，也不能授权减量 |
| 申请量 | 实际user消息的user_evidence及quantity_source | 无证据为null；中文件数有界识别，否定/跨订单保持澄清 |
| case字段 | 模型update_case提议 | source_message_id原本仅验证同用户/同轮消息锚点，不证明语义来源 |
| 确认 | 可信事件绑定preview_id、用户、hash、revision | 聊天“好的”或CONFIRMED字样不能批准任意当前方案 |
| 成功与告知 | 原事务operation回执+匹配最终notice | 模型stop或空graph.next不是业务成功；预览文案不是提交后告知 |
| 请求和用量 | aftercare_demo BudgetLedger+原始HTTP响应usage | 未知用量保留预留和暂停，不能按0；历史156次/309,920已知Token不变 |

修复1：case写入标记provenance=model_proposal。模型上下文给所有case字段保留该标记，并单独提供user_quantity_evidence的数量与真实消息ID；兼容旧case，将其同样视为提议。未取消提议记录，未放宽预览/确认/提交服务验证。
source_message_id保留兼容，含义是模型本次提议的消息锚点，不再被误称“用户已确认该值”。没有为所有字段实现语义证据抽取；当前可信数量是有限语法识别，复杂语言仍可能澄清。
修复2：“改为S1003”中文紧邻ID时，旧英文词边界没识别订单改变，导致上下文继承旧量。换成字母数字边界，识别中文邻接，拒绝更长字母数字串；跨订单清空数量。旧预览仍先失效，后端版本/资格校验保留。
修复3：明确暂不提交走共享runtime暂停事件（上轮dbd44ae），最终告知PAUSED_BY_USER/NOT_INVOKED；v3脚本只在可见问题中识别数值缺口并回复，隐藏目标不进入Agent。
修复4：旧demo reset会TRUNCATE全部表，包含真实预算。已增加REAL_LEDGER_RESET_FORBIDDEN：只要有非offline批次行就拒绝重置，包含未知预留。测试仅在aftercare_test用伪造provider记录复现和验证，真实账本未清理。现有混合演示库不要执行reset。

证据：runtime/final-acceptance-preparation保存修复前失败、首次235通过/1失败（跨订单暴露）、最终237通过/0跳过、两模式5/6原始轨迹及镜像/API烟测；索引closing-candidate-v1.json。新增上下文来源标识的模型行为效果尚无真实证据，只能由最后固定批次观察，不宣称已消除猜量。
