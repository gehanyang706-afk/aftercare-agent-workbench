# 面试与维护交接

## 一分钟项目介绍

我实现了一个电商售后多轮决策与执行工作台，用单个Deep Agent处理订单查询、取消、退货、换货及转人工。重点是把模型决策和事务权限分开：模型只有九个业务工具，必须经过版本化预览和可信确认；提交服务在PostgreSQL事务里重检资格、库存和幂等键，最终告知依据实际回执。用户改口使旧预览失效，事务后丢响应查询原操作，不盲目重写。

我保留了首轮0/4及后续失败轨迹。原四类闭环在一个真实开发版本取得4/4；最近数量批次冻结评分3/4，但其中一题先猜量被拦后才澄清，过程不干净。这些是已见开发证据，不是泛化或架构优越性证明。当前最后验收尚待批准，工作台默认离线。

## 必须讲清的七个问题

1. 为什么用Agent：根据用户多轮表达在查订单、查库存、查政策、澄清和执行之间选择；并不让模型直接写库。九工具在agent/tools.py，图和预算模型注入在agent/runtime.py。
2. 确认如何可信：HTTP会话身份+持久事件，绑定preview_id、principal、参数hash和intent_revision。普通聊天、模型参数、CONFIRMED字样都不是任意执行权限。见services/confirmation.py。
3. 为什么图结束后还能提交：应用收到实际批准事件。存在匹配HITL则恢复中断；已结束则走受控续跑，复用同一提交服务。不是无条件自动提交；重复事件只查询原回执。见agent/continuation.py。
4. 丢响应怎样不重复：事务先产生唯一operation及申请/库存副作用；响应丢失后按原preview查询同operation。数据库唯一性、锁和幂等约束决定安全，不靠模型“记得别重试”。见services/business.py、repositories/models.py。
5. 数量与事实来源：购买量和库存来自工具，申请量来自实际用户消息。case的消息ID只是模型提议锚点；上下文将其标记model_proposal，单列用户数量证据。无证据参数即使后来恢复仍计过程缺陷。见services/intent_guard.py、agent/context.py、services/quantity_audit.py。
6. 预算如何硬停：真实请求只通过BudgetLedger→PilotGateway→BailianAdapter/send_once；完整字节输入预留+输出上限，逐轮/题/批请求和Token、硬截止，SDK/HTTP重试0。未知usage保留预留并暂停。已提交后的停止只读原回执告知，停止码和失败仍保留。见llm/budget.py、llm/pilot_gateway.py。
7. 怎样证明有效：离线事务/反例测试验证工程机制；真实固定开发批次验证模型行为。冻结评分与旁路诊断分开，核对用户表达→诉求→预览→可信确认→提交→回执→最终告知。离线全过不代表LLM全过，未触发故障写未覆盖，holdout不读取。

## 可以写与不能写

可以写：实现九工具业务边界、可信确认双路径、PostgreSQL幂等事务、回执告知、独立持久预算及失败轨迹审计；给出具体版本的已见任务结果和局限。
不能写：真实退款到账/物流履约、生产部署、模型独立完成所有闭环、所有数量场景通过、holdout通过、优于baseline、成功率从0提升100%。不同场景/版本没有可比的成对实验。

维护入口顺序：runtime→continuation→BusinessService→quantity evidence→pilot runner。先复现实际原始轨迹，区分模型、工具、脚本用户、系统问题；不改评分消除失败。最后验收后停止普通功能/提示词迭代，阻断修复另记版本，新真实回归另批。
演示采用demo-script.md；结果口径采用results-summary.md；启动采用docs/operations.md。不存在新开发者必须读取的独立验收答案或密钥。
