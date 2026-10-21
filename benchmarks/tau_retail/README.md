# 固定版 Retail 离线评测入口

官方 τ²-bench v1.0.1，commit `fc0055dc4e0a316c3f83133267fbd6faaa770992`；MIT许可保留在 LICENSE.upstream。
上游工作树与隔离环境位于 runtime/benchmark-deps（不入Git），产品锁/虚拟环境未改。文本导入需要 audioop-lts，不安装 voice extras。
固定源码/政策/工具/评分/用户策略/数据文件hash见 upstream.lock.json；第三方依赖完整版本与hash见 requirements.lock。
当前所有真实校准/开发/正式test均未运行，A/B/C没有实测值。

## 已实现命令

项目根目录；以下均不发送模型请求：

```bash
.venv/bin/python -m evaluation.benchmarks.tau_retail.cli inspect --offline
# 会在隔离环境运行契约测试，需要专用aftercare_test；不得与可靠性runner/pytest并行
.venv/bin/python -m evaluation.benchmarks.tau_retail.cli contract-test --offline
PYTHONPATH=src runtime/benchmark-deps/venv/bin/python -m evaluation.benchmarks.tau_retail.cli plan --stage calibration --dry-run
.venv/bin/python -m evaluation.benchmarks.tau_retail.cli run --manifest evaluation/manifests/benchmark-v1/calibration-v1.json
# 仅对实际已有run导出，不启动模型
.venv/bin/python -m evaluation.benchmarks.tau_retail.cli report --run-id RUN_ID
.venv/bin/python -m evaluation.reliability.runner --manifest evaluation/manifests/benchmark-v1/reliability-v1.json --offline
```

带 `--execute --approval PATH --account PATH` 的 run 才可能进入真实调用，还要求显式allow_real_model_calls、精确模型/北京端点、当前账户确认、FreeTierOnly、完整hash与持久额度一致。
本轮没有该授权；勿直接执行官方 `tau2 run`，它会绕开项目入口。
重启真实run只做report/只读对账，不重新create_run或重跑episode；unknown留预留且精确模型跨角色暂停，无自动清除。
当前可执行真实入口仅支持冻结train校准；后续开发与test需实现对应冻结准备/审批协议后单独批准。

## 安装复现（下载需资源授权）

```bash
python3.13 -m venv runtime/benchmark-deps/venv
runtime/benchmark-deps/venv/bin/python -m pip install --require-hashes -r benchmarks/tau_retail/requirements.lock
# 固定上游checkout路径按upstream.lock.json；不安装tau2到产品环境
```

校准计划由真实离线payload大小估计保守预留，初步用量区间不是保证；每次请求UTF-8字节上界加framing余量，不能下调预留绕门禁。
Agent与用户共用同一精确模型时，免费余量须覆盖角色合计；未知人民币成本为null，不虚构零成本。
角色agent/user/judge/auxiliary独立账本，禁用角色预发送拒绝。所有角色计入旧Budget(project)总账；旧16/8产品限制不变。

## 当前候选与解释边界

official_tc为原版LLMAgent，harness_full_history做协议等价校准。evidence候选仅保守JSON归一化、来源/时序标注，不缓存、拦截或重执行官方工具。
full_history保留全部可见消息；fixed_window只删完整交互块，保持完整policy/schema；不能安全压缩则明确停止。
产品可显式选harness-evidence-v1复用纯模块，默认full保持历史行为。产品实际默认BM25，Retail用完整policy；没有RAG效果提升结论。
产品PG确认、事务与回执不在官方决策链中，不归因于公开成功率或Token差异。
开发池按ID散列固定20题，仅2题校准/4题tune/4题validation默认计划。独立holdout不读不跑，test正文不供开发Agent。
源代码层白名单/canary不是操作系统级安全沙箱。

## 资料与证据

四份完整规格：docs/benchmarks/implementation-v1；阶段交接：docs/handoffs/upgrade-U*.md。
本机原始轨迹/账本/测试证据：runtime/upgrade-U0、runtime/reliability；公开摘要：docs/benchmarks/reports。
M只统计实际完整20次故障触发且全部不变量通过的组；对象重建与普通函数测试不冒充实际杀进程。
所有历史产品真实结果保持原样；新公开指标不跨版本包装为旧实验改善。


## U3a 已完成与 U3b 离线候选

calibration-v2 4 episode 官方通过，78请求/509626Token；全历史 Agent 多耗6.12%，见 docs/benchmarks/reports/U3-calibration-v2-first.md。
U3b仅离线准备，见 docs/handoffs/upgrade-U3b-offline.md。无损JSON空白候选整请求体仅减1.13%字节，不是Token收益。

```bash
# 离线生成待审 train tune 计划；不生成批准、不发送请求
PYTHONPATH=src runtime/benchmark-deps/venv/bin/python -m evaluation.benchmarks.tau_retail.cli plan --stage tune --dry-run --output runtime/U3b-preparation/review-plan.json
# 冻结计划只读预检，无批准不会执行
PYTHONPATH=src runtime/benchmark-deps/venv/bin/python -m evaluation.benchmarks.tau_retail.cli run --manifest evaluation/manifests/benchmark-v1/tune-v1.json
# 只读已结束批次的 Agent 可见上下文，不读取用户/裁判隐藏输入
PYTHONPATH=src .venv/bin/python -m evaluation.benchmarks.tau_retail.replay_context --run-dir runtime/retail-runs/retail-calibration-v2 --output runtime/U3b-preparation/context-replay.json
```

当前冻结 tune-v1 尚未真实验收；项目预算不足，不能仅凭打开环境变量执行。没有新角色/预算/当前账户批准，不得添加 execute 或直接运行官方默认真实评测。


## U3c 工具可见性候选（离线已验收，真实待批）

原 tune-v1 暂缓，不再执行；新候选与限制见 docs/handoffs/upgrade-U3c-tool-visibility-offline.md。
73项离线契约、51请求体-15.48%字节及30/30历史调用覆盖不等于真实性能。
新计划 evaluation/manifests/benchmark-v1/tool-visibility-v1.json 仅train96×两配置；默认只预检，不允许自行添加execute。

```bash
PYTHONPATH=src .venv/bin/python -m evaluation.benchmarks.tau_retail.visibility_replay --run-dir runtime/retail-runs/retail-calibration-v2 --output runtime/U3c-preparation/replay-review.json
PYTHONPATH=src runtime/benchmark-deps/venv/bin/python -m evaluation.benchmarks.tau_retail.cli run --manifest evaluation/manifests/benchmark-v1/tool-visibility-v1.json
```

动态子集仅对新Agent变体，用户/judge不筛选；工具可见性不代替确认授权，环境保持完整工具目录。真实角色、额度和源码/hash须按新计划另批，普通工作台不扩大真实入口。


## U3c 已运行结果

tool-visibility-v1固定小批已结束：基线0/候选1，34HTTP/164590Token，无unknown。
候选完成两项任务，基线只完成地址；Agent成本候选高28.50%，不称Token优化成功。
细节见 docs/benchmarks/reports/U3c-tool-visibility-v1-first.md；历史待批说明仅作历史，本批不可再执行，未来真实任务须新计划及新批准。
