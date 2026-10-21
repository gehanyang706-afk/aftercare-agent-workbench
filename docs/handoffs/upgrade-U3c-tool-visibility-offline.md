# U3c 工具可见性离线交接

本轮依据《Aftercare-U3c优化建议-20261020/下一步决策与执行方案》第七节实施；是工具可见性开发准备，不是原阶段名称中的未见 validation。新范围已覆盖原 U3b 空白实验方向。未发送真实 Agent、模型用户或 judge 请求；未读 validation、Test 或独立 holdout，未提高项目 cap，未推送。

## 交付和边界

候选名 `tool_visibility_v1`，规则 `state-aware-tools-v1`。保留完整官方政策、所有用户历史、工具返回及原官方 schema；只根据过去已见订单状态选择每步给模型的工具子集。**两组每步可见工具不再相同**，这是明确的唯一主要实验变量。没有叠加 JSON 压缩、历史裁剪、输出规范、摘要、缓存、多Agent或模型发现步骤。

ObservedOrderState 只从配对成功的订单工具结果建立事实，绑定订单实体、call ID、结果 hash 和观察序号；错误/缺字段/实体不符/未知状态不能建立新事实。同订单新成功结果替代旧快照，旧观察仍保留，模型自述和用户报订单ID不作为已验证订单状态。

查询、身份、计算、转人工及用户默认地址修改工具常驻；订单写工具按多订单状态并集开放；历史用过的 schema 保留。未知状态/格式/目录映射/未决结果及同批同实体读写顺序不确定时，全目录回退，不为维持收益牺牲可达性。保守回退在该段可见历史中持续生效，可能减少后续节约，但不会封死查询路径。

Adapter 传给实际 `llm_utils.generate` 的是选中原 Tool 对象子集；原完整工具列表不改。官方 Orchestrator 保留完整环境并唯一执行工具。基线仍为原官方 LLMAgent。Gateway 由计划绑定完整目录 hash 和规则 hash，发送前拒绝篡改 schema、空集合、未知变体或 hash 变化；用户/judge不走筛选，原角色、用量和硬限保护复用。

**工具可见性不是授权。** 当前未暴露但属于官方目录的提议记录诊断，仍交给官方执行；目录外名称由官方返回错误。不补发模型请求，不替用户确认，不创建新提交服务，也不扩产品九工具权限。

## 固定官方源码核对

版本 τ²-bench v1.0.1 / fc0055dc4e0a316c3f83133267fbd6faaa770992，源码与上游 lock 复核一致。

| 工具 | tools.py 实际前置条件 | 候选暴露条件 |
| --- | --- | --- |
| cancel_pending_order | status 严格 pending；合法取消原因 | 有已见 pending |
| modify_pending_order_items | status 严格 pending；一次修改、数量匹配、库存及支付规则 | 有已见 pending |
| modify_pending_order_address | `_is_pending_order`，即状态字符串包含 pending | pending 或固定版 pending (item modified) |
| modify_pending_order_payment | 同上，且仅一条原 payment、不同支付方式及余额规则 | 同上；其他业务条件留给官方工具/政策 |
| return_delivered_order_items | status 严格 delivered；商品数量和退款方式限制 | 有已见 delivered |
| exchange_delivered_order_items | status 严格 delivered；配对数量、同产品、可用变体及支付限制 | 有已见 delivered |
| 其余10工具 | 非上述状态前置写操作；包括默认地址修改 | 始终保留 |

政策说明商品修改后订单锁定，而地址/支付的源码判断较宽。路由为保守可达性保留可能允许的原 schema，不能把“暴露”解释为准许违反政策。未知状态不按包含 pending 模糊猜测，统一回退全部16工具。官方通用查询列表也包含 get_item_details，未因原轨迹没用过就删除。

## 真实已见轨迹的离线收益

完整阅读并程序复核提供的 visible-context-profile.json，106 个文件（102 Agent请求/响应+4事件）hash 均匹配。回放只打开 role=agent 的 sent/received 数据，未打开用户/judge隐藏输入或任务正文；选择先于读取下一响应，未来调用仅用于覆盖诊断。

| 项目 | 实际结果 |
| --- | ---: |
| Agent 请求 | 51 |
| 原请求体累计字节 | 1,554,397 |
| 候选请求体累计字节 | 1,313,852 |
| 字节减少 | **15.4751%** |
| 原下一步工具调用保留 | **30/30** |
| 原回放 fallback | **0** |
| 本轮真实请求 | **0** |

提供的组件归因逐项匹配：schema 599,811（38.588%）、完整系统政策367,557、工具正文240,147、助手文本200,324、用户文本63,684、调用参数38,188、其他44,686。原实际 Agent输入431,665/输出12,523 Token不变，**没有新的provider Token或任务成功率结果**。

比 shadow 的15.0139%多7,170字节，来自对固定版 `pending (item modified)` 的明确识别；shadow当未知状态回退全目录，生产候选按源码保留宽松pending工具及历史用过工具。没有为追求这一差异增加任务规则或读取答案。

只证明这51个已见请求上路径未遗漏，不证明全部合法动作空间，也不能据30/30宣称模型成功率。离线投资筛选（约10%整请求体字节减少+已见路径无遗漏+合成边界通过）满足，但这不是最终效果验收。

## 验收、失败与修复

最终 **73 passed / 0 skipped，3.50秒**，ruff check及format通过。所有传输为假响应；PG预算契约只用 aftercare_test，未与真实批次并行。产品运行时/事务代码没有变，不重复既有U4 240次或无关产品整套测试。

| 边界 | 验证与结果 |
| --- | --- |
| 空历史、用户直接报ID、仅身份结果 | 不凭空建立订单事实；10个常驻工具保持查询通路 |
| pending/delivered/已修改/终态/未知状态 | 按固定源码映射，未知全量回退 |
| 多订单、多诉求及跨订单改口 | 能力并集，新订单查询可重新开放相关写工具 |
| 多调用部分错误/乱序结果 | 按call ID配对，失败不覆盖成功事实，未决回退 |
| 同批同订单读写 | 无执行时间证据时不按结果列表顺序假定新状态，回退全部 |
| 旧快照与模型proposal | 新的可信实体结果替代旧快照，proposal不生成观察 |
| 实际生成与fake transport | 工具子集确实进入发送参数；原Tool对象保持；基线政策/消息/schema不动 |
| 官方执行唯一性 | 查询后开放取消，只取消一次；另一路未暴露取消仍官方执行一次，目录外工具原样报错 |
| scope及角色隔离 | schema/hash/变体/基线子集改变在预留前拒绝；用户/judge不被路由 |
| 原预算保护 | 未知usage保留预留及暂停，跨批/角色、项目上限和截止契约继续通过 |
| 诊断反例 | 回放故意缺工具能报missing，不读取未来调用来补选择；损坏hash拒绝；混合文本不误计用户告知 |

保留的开发失败证据：
- `integration-tests.txt`：初版测试错误比较两次 get_tools 返回的对象；上游每次重建Tool包装，修正为检查实际Adapter输入对象身份及schema，而非修改生产Tool对象。
- `orchestrator-paths.txt`：新增测试遗漏 ToolMessage import，修复测试导入，无生产行为修改。
- `same-batch-before.txt`：实际候选缺口复现，旧实现会把同批乱序旧读当成最新结果。通用最小修复是标记同实体批次不确定、保留原始观察且全目录回退。最终测试通过，原51请求不受影响。

未发生真实失败或回归成绩回写。历史calibration-v1/v2原始hash均不变；用户已有三份报告/建议文件hash未变。

## 输出质量只做旁路诊断

版本 `visibility-replay-v1` 的 response_diagnostics记录原始finish_reason、文本长度、环境/用户路由、可见工具证据及待人工复核项；不重写响应，不给模型加输出约束，也不调用新judge。普通产品仍复用原回执告知机制，本轮未改它。

- 2 次 length 截断；5 次 >2000字符的解释（含上述2次）。这是预先固定长度信号，不等于语义评分。
- 2 处“you received a refund”及1处“exchange process is now complete”信号，涉及107官方和96官方最终告知；工具证据支持申请/账内记录，不支持真实外部到账/履约完成。需在独立输出候选中处理；本轮冻结官方分数不变。
- 107全历史及96全历史最终告知没有命中上述有限正则，不代表语义全面正确。风险信号不作为“自动裁判”，没有命中也不能当安全证明。
- 人工复核8个写调用前的可见确认：目标订单/商品、差价或目标地址、支付方式与实际调用一致，未观察到确认前写入。商品列表每次一项；不是数量歧义场景的覆盖证明。
- 107的替代变体选择、96的身份和引用另一订单地址澄清有可见信息依据；未据此判定“无效澄清可删除”。107全历史确认前有较长重复解释，记录为冗长，不取消必要确认。
- 51个响应usage未提供 cached_tokens 明细，缓存量未知；未按0计缓存命中，未创建缓存或承诺费用节省。

官方4/4结果、原Agent全历史多耗6.12%仍原样保留。旁路诊断不改reward，不能用新规则重算旧成绩。

## 新的小批真实待批计划

`evaluation/manifests/benchmark-v1/tool-visibility-v1.json`

- hash `cf13c693664f104ef6b4f82385f0a67d3b2424f447c6f704755faaaa68bdf04a`
- 执行源码 `e621e8f1ecb09f458bd21a1fbb35815a80349ad8`
- 指纹 `d11aa716ad3183e15870aa666f2209b46b9af56ac951b66987b076bd2383efa2`
- 规则hash `0027ef78d8b3e22b09fb2076c2759811f551745f9aa9869b0bfb75e1f2fcd647`
- 完整目录hash `c1b3ff400ce83557f898d8603de1ebb9aee48ebd7ab0524698a8d5068b76ac73`

仅已见 train96，固定 official_tc → tool_visibility_v1，各一次（2 episode）。基线重新运行，不能拿旧基线作新配对；这是诊断性选择，不代表Retail平均难度。可信准备器核对其有效NL断言为空，judge/auxiliary禁用，官方reward不删除。两组同精确模型、温度、用户策略、完整政策、schema参数、输出上限和评分；只改变Agent每步可见工具集合，输出质量暂不改。

| 限制 | 每 episode | 全批 |
| --- | --- | --- |
| Agent | 24 HTTP / 200,000 Token | 48 HTTP / 400,000 Token |
| 官方模型用户 | 16 HTTP / 100,000 Token | 32 HTTP / 200,000 Token |
| 所有角色合计 | 40 HTTP / 300,000 Token / 600秒 | **80 HTTP / 600,000 Token / 1200秒** |

精确模型 **qwen3.5-plus-2026-02-15**，北京、关闭思考、temperature0、seed20261020；并发1，单请求60秒；Agent输出1024/User512；重试0、换模型false、额外付费0，无模型裁判或辅助调用。所有实际修正推理继续计入预算，未知usage保留预留并暂停，不能低估预留绕过门禁。

预计 **180k–360k Token、30–55 HTTP、3–7分钟**；参考96旧两条完整轨迹约115k–117k/episode，但新用户模拟路径可能不同，字节节省不换算为承诺Token节省。上限不是预测。

普通任务失败保存首条结果继续剩余固定episode；认证/额度/协议/安全/未知usage/任一硬预算或截止异常停止全批后续请求。批内源码、prompt、场景、用户策略、评分器、预算和任务固定，不整题重跑、不追加第二题或其他架构。

当前项目cap2,000,000、settled1,000,340、reserved0，可用 **999,660**，容纳600k，无需提高cap。本轮未改任何额度。执行前仍需该新hash的Agent及模型用户授权、当前精确模型免费余量≥600k及北京FreeTierOnly新确认；本次没有批准文件、账户文件或新ExperimentRun。

原tune-v1本体/hash保留，另有tune-v1-status.json标记暂缓，入口前置拒绝TUNE_V1_SUSPENDED。不得自动执行这对真实任务或后续delivered/validation/Test。

## 运行、入口与一个完整机制

```bash
# 项目根目录：纯离线重放实际可见请求及诊断
PYTHONPATH=src .venv/bin/python -m evaluation.benchmarks.tau_retail.visibility_replay --run-dir runtime/retail-runs/retail-calibration-v2 --profile /Users/gehanyang/Documents/ChatGPT/求职/Aftercare-U3c优化建议-20261020/visible-context-profile.json --output runtime/U3c-preparation/visibility-replay-review.json
# 隔离环境离线契约，PG仅 aftercare_test
PYTHONPATH=src:runtime/benchmark-deps/tau2-bench/src LITELLM_LOCAL_MODEL_COST_MAP=True runtime/benchmark-deps/venv/bin/python -m pytest tests/benchmark_contract -q
# 新冻结计划只读预检；缺批准和当前账户时不执行
PYTHONPATH=src runtime/benchmark-deps/venv/bin/python -m evaluation.benchmarks.tau_retail.cli run --manifest evaluation/manifests/benchmark-v1/tool-visibility-v1.json
```

数据流：原可见消息→`observe_visible_history`提取来源绑定状态→`select_tool_names`合并订单能力/保守回退→Adapter选原Tool对象→官方generate→CompletionBridge验证固定目录子集及规则hash→原持久Ledger预留→fake/未来获批真实传输→官方Orchestrator唯一执行→实际ToolMessage回填。

核心入口：`tool_visibility.py`（纯函数/版本）、`adapter.py`（真正选择Tool对象）、`model_bridge.py`（schema范围/提议诊断）、`runner.py`（角色/预算/Trace）、`visibility_replay.py`（可见输入重放与输出风险信号）。实际工作台/旧产品九工具服务保持原边界，没有新增部署入口。

完整机制举例：用户直接报订单ID时仍只有10个常驻工具，系统不信其自述状态；模型可调用官方查询，成功得到pending后下一次请求开放对应写工具；用户确认仍由模型和完整政策处理，工具执行仍由官方环境判断。模型若无视可见集合提出官方工具，也只被记录并交回官方环境，不借可见性模块另造授权逻辑。

未覆盖：新候选任何真实模型行为、delivered真实配对、广泛多诉求/数量表达、模型是否因schema变化新增幻觉、正式validation/Test成功率或Token收益。合成测试不代替这些证据；这对真实任务成功后也不能声明总体成功率提升。项目收尾不以跑满40题或必须得到正收益为前提。
