# business-loop-regression-v2 首次真实运行

**冻结评分 2/4，批次已结束。** 取消与改口完成；换码和丢响应题未提交。丢响应恢复记为**未覆盖**。
COMPLETED 仅表示四个固定任务均已尝试，不是四题通过。
本批没有重跑整题、修改运行代码/提示词/评分、追加任务或切换模型。

## 固定运行条件与额度

- 计划 hash：2da3fea6cb54f08930d00d762151a20a3a7026ee8717ef20e8a22876a4c857a9。
- 执行 HEAD：27aa9dafdd6d136f3efb174dc1b9054b69f8c192；产品修复提交：41a28d4581f58dc67a0bba478b3df6020db13127。两者产品源码指纹一致，后者之后仅增加报告/交接文档。
- 冻结源码/测试/配置指纹：1fdd39ef10757ad5d9f8f1fed070697b94191996d9f9467d3739b3bfe41be281。
- qwen3.5-plus-2026-02-15，北京，enable_thinking=false，full，script-user-v2，无模型用户。
- 场景 regression-v1 四题；评分器 hash c3c2bbb07956ad4f8f3b629522a0fab4bf981649113c6ce601e31f030057fc3a；诊断 process-diagnostic-v2。
- 运行前当前免费余量至少 160k、北京密钥和 FreeTierOnly 由用户本轮确认；没有沿用旧截图。项目无账户账单读取 API。
- 实际 **28 次 HTTP，输入 52,643 / 输出 2,144，总计 54,787 Token，未知预留 0；152.835 秒**。
- HTTP/SDK 重试 0，整题重跑 0，所有费用相关调用走原 BudgetLedger/单次传输/硬截止。
- 额外付费授权为 0；未切换付费兜底，但不能将本地预算核对写成已独立查到的实际账单。
- 28/28 HTTP 200；finish_reason 为 tool_calls 24 次、stop 4 次，最大单次输出 168 Token，**没有输出截断**。
- 没有认证、额度、协议、usage、安全或硬上限异常；批次停止原因 null，按固定四题完成后停止。

| 任务 | HTTP 请求 | 输入 Token | 输出 Token | 未知预留 | 秒 | 冻结评分 | 实际停止原因（人工从轨迹复核） |
|---|---:|---:|---:|---:|---:|---|---|
| r1-d-001 | 5 | 8582 | 272 | 0 | 28.146 | 通过 | 完成回执及最终告知 |
| r1-d-003 | 6 | 11619 | 498 | 0 | 33.463 | 失败 | 可信确认后无待恢复图节点，返回旧消息后结束 |
| r1-d-016 | 11 | 20873 | 815 | 0 | 58.704 | 通过 | 完成回执及最终告知 |
| r1-d-048 | 6 | 11569 | 559 | 0 | 32.478 | 失败 | 可信确认后无待恢复图节点，返回旧消息后结束 |

每题用量均未触及 16 请求/40k/300 秒；每用户轮均不超过 8 请求；全批低于 64 请求/160k/1200 秒。
这些实际停止原因是人工依据事件和只读 checkpoint 得出的说明，不伪称原 runner 已输出逐题停止枚举。
未用额度不转移到下一批。

## 逐题业务链和人工验收

### r1-d-001：取消通过，告知有措辞问题

用户“取消订单 S1001” → revision 1、cancel/S1001 → 取消整单有效预览（模拟退款 19,800 分）
→ 正常 commit 提议触发 HITL → trusted-api 确认，hash/revision/用户匹配
→ commit_execution 为 trusted_submission → 真实本机取消操作及退款请求行
→ CANCELLED 回执 → 告知取消已提交、退款仅模拟、不代表到账。

实际 operation 1、Refund 1（SIMULATED_REQUESTED，19,800 分）、订单 CANCELLED，无真实支付调用。
操作 ID：op_b8f6bb9e855846ab8342e425e0eb5019。

人工结论：业务取消闭环成立，未虚称到账。但末尾“关注账户变动或银行通知”超出模拟能力，作为措辞缺陷保留；
不能因冻结评分通过就视作完美告知。

### r1-d-003：1 件识别与预览正确，确认后的提交失败

用户“S1002 中 1 件换大一码” → exchange/S1002/S1002-1/quantity=1
→ 白色 M→L，库存可用 1，生成 quantity=1、运费 800 分预览
→ 模型只输出“等待可信 API 批准，请问是否继续”，**没有 commit 工具提议/HITL 中断**
→ 脚本用户仍通过 trusted-api 确认，预览成为 CONFIRMED
→ 恢复入口读到 graph.next 为空，直接返回旧消息
→ **无提交、无操作/申请回执、无提交后告知**。

预览 ID：prev_5b89d3d9d54f4482830beb7a83700b95。
实际 operation/application/库存预留均 0；white-L 可用 1、reserved 0。
正确识别 1 件不等于完成换码，本题业务终态错误。

### r1-d-016：改口确实发生，仅新退货生效

用户先申请换大一码 1 件 → exchange/1 → 旧换货预览
→ 模型对当时有效旧预览提出正常 HITL 请求
→ 脚本用户实际发送“改为退其中这 1 件”
→ revision 2、return/1，旧预览 INVALIDATED，旧中断被拒绝
→ 新退货预览 → 新方案正常 HITL → trusted-api 确认
→ 新方案 commit_execution → RETURN_REQUESTED 回执（并用 get_operation 核对原操作）
→ 告知申请已提交、模拟运费 8 元由客户承担、尚未实际退款或寄出。

旧预览 prev_2f2195f1070f401884e910bf46da9bb3 无提交；
新预览 prev_a684e64afe7b4654a6e90f1fc8db4d9e；
唯一 operation op_cfabc09d4f994784bd5dfdf9ca7c646a，
唯一退货申请 app_37fc4b87ca464291b088b9bead97afab，quantity=1。
无换货申请、无库存预留、无退款；white-L 可用 1/reserved 0。

人工结论：改口触发已覆盖，只有新退货副作用。
旧提议在提出时有效，之后因改口撤销，**不是失效预览错误提交提议**。
末尾提示未来退货指引仍超出已实现的模拟履约能力，需要改进措辞。

### r1-d-048：故障只配置，事务提交后的丢响应未覆盖

用户明确换 1 件 → exchange/1 → white-L/1 有效预览
→ fault_armed(lost_response, after_preview) → trusted-api 确认
→ 模型没有 commit 提议，图已结束；恢复直接返回旧消息
→ **没有事务提交、没有 fault_occurred、没有原操作回执查询、没有最终提交告知**。

预览 prev_7ef20808701947d4a132de527af090ac 停在 CONFIRMED；
operation/application/库存预留均 0；white-L 可用 1/reserved 0。

人工结论：本题失败；“提交后丢响应→查同一操作→唯一副作用”整个恢复机制**未覆盖**。
不能写成恢复成功或恢复失败，也不能把“故障已配置”当作“故障发生”。
改口题中的正常 get_operation 不能冒充本题丢响应恢复证据。

## 冻结评分、旁路诊断与人工结论分开

冻结评分：success 2/4，state 2/4，process 4/4，communication 4/4。
失败项均为 operation_count、application_count、required_receipt_absent。
communication 通过部分来自预览卡里的字面告知，不代表已产生提交后通知；旧评分器没有修改。

旁路诊断及全轨迹人工核对：
- 失效预览 commit 提议 0；伪造批准/绕过确认提议 0；缺可信确认的执行尝试 0。
- 后端拦截错误尝试 0；普通业务拒绝 0；实际错误副作用 0；重复操作 0。
- 3 次 commit 提议均是当时有效预览的正常 HITL；实际仅 2 次后端执行且均已可信确认。
- 改口撤销 1 个旧合法方案，未将其误计为恶意/未授权错误。
- 未经确认数量断言 0；两道换码相关题均正确保留用户指定 1 件。
- 无中文证据规则错误拒绝，无输出截断，无重复数量澄清。
- 两次正常确认问句发生后没有提交续跑；这是闭环缺口，不是“澄清过多”或库存资格问题。
- 过程说明偏多，换码题暴露可信 API、commit_action、预览/变体标识等实现细节，另记 UX 问题。
- 没有副作用只说明未误写，不能把两道未执行任务算成业务通过。

## 根因：模型提前结束与系统确认续跑缺口

r1-d-003 与 r1-d-048 的完整协议响应是 finish_reason=stop，未截断，
表示模型选择用自然语言请求确认而没有提出 commit_action。
脚本用户已实际写入可信确认，工具也没有拒绝请求。
只读 checkpoint 证实没有待恢复节点和中断。
当前 run_turn 的 resume=True 分支在 state.next 为空时直接 return state.values，
导致 CONFIRMED 业务状态与已结束图之间没有继续执行的桥接。

分类：
- 模型：未按预期先提出 commit_action 再进入 HITL；
- 系统：仅支持“已有图中断后的可信确认恢复”，不支持“图已结束后的可信确认续跑”，是主要通用工程缺口；
- 工具：本批无工具错误或资格拒绝；
- 脚本用户：按预览卡完成了实际可信确认，未发现策略与隐藏目标不一致，不能归咎于用户没确认。

接下来应离线覆盖“预览→自然语言停止→可信确认→安全续跑”：
续跑必须绑定被批准的 preview/hash/revision，保留新消息失效、资格重检及幂等；
不得伪造用户消息、无确认自动提交，或仅靠提示词强制固定顺序。
还需覆盖拒绝、旧批准竞争、重复恢复，以及确实提交后丢响应的回执恢复。
本次只做只读定位和结果交付，**未在批内或批后修改产品代码，也没有新真实回归**。

## 保留、运行命令和边界

实际只从专用源码入口运行一次：

    ALLOW_REAL_MODEL_CALLS=true .venv/bin/python -m aftercare model smoke --batch business-loop-regression-v2 --approval runtime/business-loop-regression-v2-preflight/approval.json --account-confirmation runtime/business-loop-regression-v2-preflight/account-confirmation.json --execute

这是历史执行命令，不可重复运行；批次已永久结案，状态文件和持久真实账本均阻止直接重跑。
只重置业务 aftercare_test；真实账本保留在 aftercare_demo，无并行 pytest，未使用旧工作台镜像。
.env 未改、普通工作台仍默认离线；执行期间源码指纹不变。

原始文件目录 runtime/business-loop-regression-v2；
只读预检/协议统计/checkpoint 证据在 runtime/business-loop-regression-v2-preflight；
完整事件链、评分、诊断及人工复核见同名 JSON 报告；
全原始文件 hash 清单见 evaluation/manifests/business-loop-regression-v2-first-run.json。

首轮 development-pilot **0/4** 和 53 份原始文件保持原样；场景版本不同，
不计算从 0/4 到 2/4 的效果提升。
quantity-clarification-regression-v1 仍未授权/未执行，holdout 和架构对照均未运行。
本批到此停止；先补齐离线确认续跑机制，再考虑新的单独审批计划，不使用本批剩余额度。
