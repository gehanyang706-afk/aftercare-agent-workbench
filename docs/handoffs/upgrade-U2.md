# U2：上下文、测量与校准准备

纯ContextPolicy提供full_history、fixed_window、evidence_projection；完整policy/schema不裁剪；工具批次按call ID整组保留，所有用户改口保留。
首版evidence候选只做可逆JSON空白归一化，不删金额/地址/支付/状态/选项/错误字段，也不缓存或拦截官方工具。
这是保守的可测候选，尚无真实优化收益；没有证据时不猜测“重复结果”而删字段。超预算明确拒绝，不静默裁剪。
产品显式harness-evidence-v1复用同一个纯模块；旧full不变。工厂明确选择bm25/full-policy/hybrid-rerank并记录实际profile；Retail始终完整官方policy，不宣称RAG收益。

Trace为追加事件+hash寻址payload：模型预留/发送/结算/未知、上下文、工具、终止、评分。原始本机记录不入Git。
metrics输出planned/attempted/completed/not_run、角色分账、配对四格、双方成功成本、Wilson区间；unknown或覆盖不完整不报精确节省率。
不同version/trial、重复episode拒绝合并；不将用户Token归Agent，不把早失败省Token直接作为晋级依据。

开发池只按固定train ID散列确定20题：12 tune/8 validation，实际默认4+4；calibration为tune前2题×官方基线/未优化适配器。
CLI：inspect --offline、contract-test --offline、plan --stage calibration --dry-run、run（缺execute/批准只preflight）、report。
具体命令见benchmarks/tau_retail/README.md。U3计划必须在U4修复后重新冻结source/lock/scorer/任务内容hash。
没有创建approval/account确认文件，没有真实请求。未知价格留null，未取得A/B/C。


补充核对：校准固定任务107/96的实际reward_basis为DB+NL_ASSERTION。107需1次裁判、96无需实际裁判请求。
已离线接入共同裁判配置（提议Qwen同精确版本替代官方默认GPT-4.1，prompt/评分不变），纳入待批角色；没有真实调用。
官方Orchestrator会给LLMAgent/User设置seed，适配器已复用同一行为；原始payload等价与三角色seed/账本边界spy均通过。
后续隔离契约共23 passed，包含历史bailian-beijing-compatible provider别名与旧暂停不隐式解除的反例。
