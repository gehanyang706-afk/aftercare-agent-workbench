# 6A business-loop-regression-v2 首次真实运行交接

本批已结案，冻结评分 2/4；取消、改口通过，直接换码和丢响应题未提交。
28 次真实 HTTP，输入 52,643 / 输出 2,144，共 54,787 Token；未知预留 0，耗时 152.835 秒。
原首轮 0/4 保留；场景版本不同，不计算效果提升。
未运行数量澄清批次、holdout、模型用户或架构对照，不重跑任何整题。

## 版本、入口与验证

精确模型 qwen3.5-plus-2026-02-15，北京，关闭思考，full/script-user-v2。
执行 HEAD 27aa9dafdd6d136f3efb174dc1b9054b69f8c192；
产品修复提交 41a28d4581f58dc67a0bba478b3df6020db13127，源码指纹与冻结报告完全一致。
计划 hash 2da3fea6cb54f08930d00d762151a20a3a7026ee8717ef20e8a22876a4c857a9。
源码/提示词/场景/用户策略/诊断/评分在运行中均未改变，所有请求经原预算账本及硬截止。

本批实际历史入口如下，批次状态/账本已关闭，不能再次执行：

    ALLOW_REAL_MODEL_CALLS=true .venv/bin/python -m aftercare model smoke --batch business-loop-regression-v2 --approval runtime/business-loop-regression-v2-preflight/approval.json --account-confirmation runtime/business-loop-regression-v2-preflight/account-confirmation.json --execute

运行前用户本轮确认免费余量至少 160k、北京密钥、用完即停；不是沿用旧账户记录。
没有并行 pytest，仅重置 aftercare_test，aftercare_demo 账本保留。
没有修改 .env，普通工作台仍默认离线；未使用旧阶段 5 工作台镜像。

28/28 HTTP 200，24 次 tool_calls / 4 次 stop，最大单次输出 168 Token，无截断或 usage 异常。
无自动重试、整题重跑、额外调用、模型切换；未触发硬停止条件。
原始 65 文件（含 28 对请求/响应）已冻结 hash；旧首轮 53 文件核对未变。
完整报告和逐题事件见 docs/experiments/business-loop-regression-v2-first.md/.json；
hash 清单在 evaluation/manifests/business-loop-regression-v2-first-run.json。

## 业务链和失败机制

取消：用户取消 S1001 → 有效 case → 整单预览 → 正常 HITL → trusted-api → commit → CANCELLED
→ 仅模拟退款请求告知；实际退款行 SIMULATED_REQUESTED，19,800 分。

换码：明确换 1 件 → 正确 L/1 预览 → 模型自然语言询问确认后结束 → trusted-api 已确认
→ 图无 next/interrupt，恢复返回旧消息 → 无提交、回执、申请或库存预留。

改口：旧 exchange/1 预览和正常提议 → 实际用户改为退 1 件 → revision 2/旧预览失效
→ 新 return/1 预览 → 仅新方案可信确认/提交 → 唯一退货申请及原回执 → 最终告知。
旧合法提议在改口后撤销，不是失效预览错误提交尝试。

丢响应：正确 exchange/1 预览 → fault_armed → trusted-api 已确认
→ 同样未进入提交 → 无 fault_occurred 或原操作查询；恢复机制“未覆盖”，不写恢复失败或成功。
实际 application/operation/stock reservation 均 0。

核心机制：可信批准是业务事实，不等于 LangGraph 存在待恢复中断。
run_turn 当前在 resume=True 且 state.next 为空时直接返回，
导致“CONFIRMED 预览、已结束图”成为静默停滞。
模型没有提出 commit 是触发因素；缺少安全的确认续跑桥接是通用系统缺口，
不能归因于库存、用户未确认或中文证据误拒绝。

## 评分、诊断和人工复核

冻结 success/state 2/4，process/communication 4/4。
旧字面告知评分能被预览卡满足，不证明两题已有提交后通知，未修改口径。

旁路和原轨迹核对：失效提议/伪造批准/缺确认执行/后端拦截错误尝试/错误副作用/重复操作均 0。
仅 3 次正常 HITL 提议，实际后端执行 2 次且均已可信确认。
没有输出截断、重复数量澄清或中文证据错误拒绝。
取消尾句“关注银行通知”超出模拟系统能力；换码告知暴露可信 API 和 commit_action 等内部细节。
没有错误副作用不能替代成功完成，两题失败不得省略。

## 下一步及交付状态

已实现：现有固定九工具、事务预览/确认/提交、预算、诊断和评测入口保持原版本。
已验证：本批取消及改口真实闭环；无错误提交/重复副作用；数量 1 的 case/预览一致。
待验证：普通换码申请和库存预留闭环；实际提交后丢响应恢复；数量歧义两题。
未实施：确认后无待恢复图节点的通用续跑修复；新真实回归；holdout/架构对照。

下一步先离线复现/修复确认续跑，覆盖拒绝、旧确认、新消息、重复恢复及真实提交后丢响应替身；
保留所有身份、hash/revision、资格及幂等校验，不伪造用户消息或无确认自动执行。
若修改源码，后续真实计划必须重冻指纹并重新明确批准，不能消耗本批未用额度。
当前 quantity-clarification-regression-v1 仍未授权，不自动执行。

五个代码/证据入口：
1. src/aftercare/agent/runtime.py:138：已结束图的 resume 返回分支。
2. src/aftercare/services/business.py：可信确认、事务和幂等。
3. evaluation/evaluator/runner.py：脚本用户确认与 resume 协议。
4. evaluation/evaluator/diagnostics_v2.py：提议/执行/故障分开。
5. runtime/business-loop-regression-v2-preflight/checkpoint-readonly.json：原图只读根因证据。

可复核任务：打开失败题事件链，比较 preview_confirmed 与缺失的 commit_execution，
再对照 next=[]/pending_interrupts=0；不要用真实模型或恢复真实业务来复现。
理解检查：CONFIRMED 为什么还可能没有提交？旧合法提议被改口撤销为何不算违规？
fault_armed 为什么不能证明丢响应恢复已覆盖？
