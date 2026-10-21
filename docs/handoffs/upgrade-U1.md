# U1：官方契约与受保护账本

实现：官方 HalfDuplexAgent 适配器、原版 LLMAgent 基线、明确白名单 factory、仅 completion 边界传输桥。
官方 Orchestrator 是唯一工具执行者，保留官方系统模板、消息转换、解析、工具和评分。产品九工具边界未放宽。
隔离环境使用固定 LiteLLM1.82.6，官方源码无修改。Python3.13 导入所需 audioop-lts0.2.2 已入 hash 锁，不安装语音 extras。

离线验收：官方协议3项（完整编排器/评分、相同输入 payload 等价、乱序多call与空文本）；桥接2项（先结算再拒绝坏协议、缺usage留预留）；纯上下文/指标6项；PG账本4项均通过。
证据 runtime/upgrade-U0/{official-tests,ledger-tests,pure-tests}.txt。后续U2/U4修改仍须最终复核。
运行入口：隔离环境 PYTHONPATH=src:runtime/benchmark-deps/tau2-bench/src LITELLM_LOCAL_MODEL_COST_MAP=True python -m pytest tests/benchmark_contract。

新增0006增量迁移只创建实验表；ExperimentLedger仍使用原Budget(project)总额度，不改旧BudgetLedger的16/8限制。
数据流：可信runner授权→run/episode/角色维度→project与共享模型额度锁→持久ModelCall→唯一HTTP传输→先usage结算→协议解析。
unknown保留预留、共享精确模型暂停，跨batch/role/restart拒绝；别名归一化，账户确认以账本watermark为基准。
源码入口 evaluation/benchmarks/tau_retail/{adapter,baseline,model_bridge}.py、src/aftercare/llm/experiment*.py。

限制：这是离线协议证据，没有官方真实分数。独立test/holdout未读未运行。未知用量手工对账解锁工具尚不提供，默认持续暂停。
下一步U2冻结trace/指标与2×2校准计划；U4实际进程与故障验证后再重新冻结源码。
