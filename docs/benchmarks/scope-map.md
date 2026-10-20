# 升级职责边界

|模块|职责|禁止输入/行为|
|---|---|---|
|官方 Orchestrator/Environment|唯一官方工具执行、初态、对话|适配器自行执行工具|
|official_tc|原版 LLMAgent 决策|GT/Solo、改变政策或工具|
|harness|纯可见上下文选择、call-ID成组|task、隐藏目标、参考动作、DB全量|
|官方 user|隐藏用户目标、官方用户策略|状态混入Agent|
|可信 runner/evaluator|Task、奖励、冻结顺序|答案进入模型prompt|
|ExperimentLedger|持久预算、共享模型额度、暂停|绕开旧project总账、未知用量按0|
|产品 BusinessService|身份/批准/资格/版本/幂等提交|以benchmark替代产品批准|
|reliability|仅aftercare_test，离线故障证据|清空demo、模型请求、杀不属于测试的进程|

无操作系统级 oracle 隔离声明；输入白名单和 canary 是代码层隔离。
