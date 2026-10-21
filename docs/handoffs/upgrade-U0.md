# U0：升级盘点与隔离

基础提交 671a8d4f6ce00d6b1274d4710ed7ec9b5cef5bc6；分支 upgrade/public-retail-v1。
四份规格原文保存 docs/benchmarks/implementation-v1。升级范围已追加 AGENTS，旧保护保留。
既有一份报告修改、两份未跟踪策略文档保持原样；逐文件 SHA256 在 runtime/upgrade-U0/inventory.json。
当前 Python 3.13.14，deepagents 0.7.28、LangGraph 1.2.16；以实际安装为准，不沿用旧版本记忆。
PG17 容器已就绪；8128 旧离线 app 运行，worker 当前未运行。没有重启或修改用户容器。
只读真实账本：156 请求 / 309920 Token / unknown 0。快照 runtime/upgrade-U0/ledger-before.json。

上游固定 v1.0.1 / fc0055dc4e0a316c3f83133267fbd6faaa770992，tag 实际解引用一致。
许可/源码/拆分 hash：benchmarks/tau_retail/upstream.lock.json。开发池仅依据 split ID 确定，未读取 test 正文。
用户批准下载固定源码与隔离文本依赖；无全局安装、权重、voice extras。源码 sparse 工作树只保留源码、文档、测试、Retail。
初次完整 checkout 实际861MB（其中数据734MB），超出估计；已收窄工作树，不将完整上游打包进产品。
隔离锁与环境准备中，产品 requirements.lock 与 .venv 不改；原237项验收不在U0重复。

核心边界：产品 PG 事务证据与官方决策 benchmark 分开。官方 Agent 只看 policy/tools/可见消息，唯一工具执行者是官方 Orchestrator。
下一阶段 U1 建立官方契约、受保护多角色账本、离线传输；U2 做测量与上下文，U4 做真实进程故障。
本轮真实调用为0；旧六题及所有真实评测均未执行。
