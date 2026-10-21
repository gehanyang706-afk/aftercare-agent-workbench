# U3b 离线候选与待批计划

## 本次结果

仅做离线工程，没有真实请求、默认官方评测、模型用户/裁判执行、Test、validation 或独立 holdout。历史两次 U3 原始文件 hash 均不变；真实账本仍 238 请求 / 831,779 Token / unknown 0。普通工作台仍默认离线。

候选 `json-whitespace-lexeme-v1` 仅去掉工具 JSON 字符串外的空白。完整政策、工具 schema、所有用户原话/确认/撤回、模型历史、工具字段与调用 ID 原样保留；不添加提示词、规划器、缓存或新的模型推理步骤。

原实现 parse→重新序列化会损失重复键、高精度数字、字段顺序或原始转义。失败测试先保存在 `runtime/U3b-preparation/json-before-fix.txt`；新实现只用解析作有效性检查，序列化来源仍是原始字符，逐字符删除字符串外空白，非法 JSON/工具错误原文保持不动。

39 项 Benchmark 契约通过（6.49 秒），产品环境共享 ContextPolicy 回归 1 项通过（2.69 秒），ruff 校验通过。覆盖精度/重复键/字符串空白/转义、不规范 JSON、安全消息块、官方请求边界等价、保留原始 state、上下文选择 Trace、固定 train 范围及项目预算不足前置拒绝。最初混用 benchmark 环境收集产品测试失败（缺 deepagents），已分别使用两套原有环境完成，不安装新依赖。未重复无关全量或 U4。

## 实际上下文重放

只加载 calibration-v2 `model.sent` 且 role=agent 的可见请求，先校验 payload 路径与 hash；不加载模型用户或 judge 的输入，不读取任务答案。51 次原始 Agent 请求：

- 原请求体累计 1,554,397 字节，候选 1,536,865，减少 1.1279%。
- 12 次请求没有可删空白，内容完全相同；其余只改变工具 content 中字符串外的空白。
- 原始请求未改写，所有用户消息、系统政策、tools/schema、参数、工具配对及所有消息块保留；实际官方转换接缝另有合成请求等价测试。
- 字节数不是供应商 Token 数，更不是任务成功率。先前全历史较官方多耗 6.12% 与模型用户路径和生成差异有关，不能用本候选离线重放声称已消除。

可重复命令（完全离线）：

```bash
PYTHONPATH=src .venv/bin/python -m evaluation.benchmarks.tau_retail.replay_context --run-dir runtime/retail-runs/retail-calibration-v2 --output runtime/U3b-preparation/context-replay.json
PYTHONPATH=src:runtime/benchmark-deps/tau2-bench/src LITELLM_LOCAL_MODEL_COST_MAP=True runtime/benchmark-deps/venv/bin/python -m pytest tests/benchmark_contract -q
PYTHONPATH=src ALLOW_REAL_MODEL_CALLS=false .venv/bin/python -m pytest tests/agent_contract/test_shared_context_profile.py -q
```

数据流：官方可见历史→纯 ContextPolicy→完整块选择清单及来源 hash→官方消息转换→相同受控预算桥接→官方 Orchestrator 执行工具。候选保存原始 state，投影仅用于下一次请求；上下文 Trace 记录在私有本机目录。原始用户角色/裁判隐藏提示不进入投影。

入口：`src/aftercare/harness/context_policy.py`、`evaluation/benchmarks/tau_retail/replay_context.py`、`adapter.py`、`runner.py`、`cli.py`。本次修复通用纯投影，不改产品事务、HITL、资格或幂等服务，也未重建/扩大普通工作台真实镜像入口。

## 已冻结、尚未授权的 tune-v1

计划文件 `evaluation/manifests/benchmark-v1/tune-v1.json`。

- hash：`b8f77a03771ff63781c0ed1cde8ef5ee87a6a69000f8cac8d60f260d7bd2014b`。
- 执行源码：`76f72e3d0fce61e547e968058c3379eb643aae95`；指纹 `c59d33cd264808cc0000eeecbb60a44595d459aac04b08e5daf33f8615f85d78`。
- 固定四题 107、96、112、30，每题 official_tc / harness_evidence 各一次，固定 seed 顺序见 manifest，trial 0，共 8 episode。107/96 为已见校准任务；112/30 本次由可信准备器读取 train 以核定角色，无场景特判。
- 两组相同完整政策、模型、工具、输出上限、评测方式及官方用户；唯一决策输入差异是工具 JSON 空白，不选择性改 prompt。
- 所有实际角色精确 qwen3.5-plus-2026-02-15，北京、关闭思考、temperature 0。模型用户沿用官方 UserSimulator；必要 judge 仅 107 两个 episode，官方 NL 判据不删除，使用相同已列 Qwen 代替默认 GPT-4.1，并记录该配置差异。

| 角色 | 每 episode 请求 / Token | 全批请求 / Token | 单次输出 |
| --- | --- | --- | --- |
| Agent | 24 / 200,000 | 192 / 1,600,000 | 1024 |
| 模型用户 | 16 / 100,000 | 128 / 800,000 | 512 |
| 必要裁判（仅107） | 1 / 100,000 | 2 / 200,000 | 1024 |

全批硬上限 **322 HTTP、2,600,000 输入输出 Token、4800 秒（80 分钟）**；每 episode 最多 41 HTTP / 400,000 Token / 600 秒，未需裁判的题另受 40 HTTP / 300,000 角色合计约束。单请求60秒、并发1、所有重试计数但显式重试设0、不换模型、无辅助/自动review、额外付费0。保留既有预留保护，不为省额度降低安全余量。

预计全批 0.8M–1.52M Token、约 120–200 请求、15–35 分钟，仅参考四个完整校准轨迹（单 episode 115k–147k、18–20请求、101–142秒）；新任务可能显著不同。硬上限不是消费预测。

普通 reward=0 保留首次结果并继续剩余固定 episode；认证/额度/协议/安全/unknown usage/任一硬限立即停后续真实请求。不得重跑整题、换角色取额度、转移旧批剩余预算。先保留所有结果，批内不改源码、prompt、场景、用户策略或评分器。

只支持冻结 calibration/tune train 入口，其他 split/variants/任务次序被预检拒绝；validation/Test 仍未开放。计划生成与 run 缺批准默认预检，无网络。不得直接用官方 CLI 发起默认真实评测。

## 预算缺口及建议

当前项目 cap 2,000,000、settled 1,000,340、reserved 0，可用 **999,660**；要覆盖 tune 硬上限，缺 **1,600,340**。若单独批准提高项目累计记账 cap，按当前水位最低需 **3,600,340**。本次没有改 cap，计划内标记不具备预算变更授权，预检会拒绝预算不足，不能只靠新批 manifest 绕过总账。

账户当前余额未知，不沿用上次 140 万确认推算。若以后执行，需同时有：本新 hash 及三个角色的明确批准、当前精确模型至少260万免费Token和FreeTierOnly新确认、项目cap另行批准并审计调整，且执行时水位足够。本次未创建该批批准、账户确认或 ExperimentRun。

**建议暂缓这次真实优化实验。** 当前只有约1.13%整请求体字节减小，潜在收益可能被对话差异淹没；不能为获得简历提升数字持续花预算或继续加机制。候选和计划可审查，先权衡成本再批准。若保守保留官方/全历史作为最终候选，也应公开写出未发现优化收益；后续正式公开评测仍须独立计划，不跳过验证直接称Test完成。

## 一个完整机制：为何不能解析后再输出

工具返回中的金额、高精度数值、重复键或转义是观察证据的一部分。JSON 解析通常把对象装进字典、数值装进浮点；再输出可能覆盖重复键或舍入。修复先检查是不是JSON，再扫描原文本：字符串内部（含转义）逐字符原样输出，字符串外只删除空白。因此事实文本不重建、确认不裁剪，模型仍拿到所有来源，只少付空白的上下文体积；是否真的少付Token必须另由真实成对实验验证。
