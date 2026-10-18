# 阶段 6A：闭环 v3 首次结果与离线修复交接

2026-10-18。第一批真实 2/4；第二批因条件不满足未启动。全部真实调用已停止。
详见 ../experiments/business-loop-regression-v3-first.md 和同名 JSON。
历史首轮 0/4、v2 2/4 与本批 2/4 分开保留，不计算跨版本提升。

## 状态与版本

- 已执行：business-loop-regression-v3，批准 hash b4f837fb027c7a8484303b58a7f35edb0a59075c5705c890cfc4532301256fa1。
- 执行产品版本 19fe7adc8ac3656bc00f238cd8a9ea7f8d99bc44；实际文档 HEAD 8945c6d；源码 cc773b0711a785f61001e79507555fa56779104f0cf56b49bce92844b7c9befb。
- 本批 19 请求、输入 35,392 / 输出 1,141 Token、90.701 秒、未知预留 0。
- 取消通过；换码失败，重复已知事实澄清；改口失败且未触发；丢响应在事务后发生并查回原回执，唯一申请及库存预留。
- 条件批准的 quantity-clarification-regression-v2 未启动，不沿用其批准到新代码。
- 后续离线修复提交 639c8fa68db9ffcf20882f6224d9602bc3b09b11，源码 d785eb296286d6e6832c5aaf727ad279dd2ab7a3c331fec32026cdf667e2f265。
- user-policy-v2、旧 grader、三份开发场景、旧 v2/v3 诊断未变；新增 process-diagnostic-v4，确认/告知版本仍 v1。
- 现有 8128 容器仍为上一轮离线修复镜像，本轮未重建；本机源码候选已更新。普通工作台默认离线，无新增真实入口。

## 完整机制：事实澄清不能替代事务批准

用户明确 1 件和大一码 → 模型查订单解析目标 → 更新有效诉求 → 后端校验当前用户证据并生成预览
→ 用户批准绑定 preview/hash/revision/身份 → 应用恢复匹配中断或受控处理已结束的图
→ 同一事务服务校验资格/版本/库存并幂等提交 → 查询实际回执 → 应用保存匹配最终告知。

本批两题在“模型查订单”后错误地再次询问已有事实，所以没有预览，不能进入可信批准和续跑。
这与上一轮“已有批准但图结束”是不同触发点；不能靠后台提交修补没有预览的任务。
通用提示词现在只要求澄清缺失/冲突信息，模型仍可能不遵循；安全规则和回执告知继续由应用保证。
新增诊断只观察数量重复澄清，不授权、不改评分、不强制模型循环，不代表真实问题已解决。

## 验证与证据

先保存原始首轮 47 文件清单，后进行离线修改；旧首轮 53 文件、v2 65 文件和用户已有文档编辑均核对未变。
新诊断复现 3 个失败反例，再通过 12 项新旧诊断测试；runtime 重放验证 WAITING_USER 不伪造完成。
全量 152 passed / 1 skipped / 49.33 秒，唯一健康检查单独补验 1 passed / 0.14 秒。
default 与 preview-stop 两种离线模式各六题 6/6；不等于真实模型质量。
命令见主报告，测试与评测串行；日志 runtime/business-loop-regression-v3-repair。
freeze 见 evaluation/manifests/business-loop-regression-v3-offline-repair-freeze.json。

## 核心代码入口

1. src/aftercare/agent/instructions.py：事实澄清与提交批准的通用约束。
2. evaluation/evaluator/diagnostics_v4.py：不回写评分的数量重复澄清观察。
3. src/aftercare/agent/continuation.py：复用原提交服务的绑定事件续跑（本轮未修改）。
4. src/aftercare/agent/presentation.py：真实回执生成用户最终告知（本轮未修改）。
5. src/aftercare/llm/regression_scope.py：关闭旧 scope，限定新待批计划及源码指纹。

## 体验与理解

可在默认离线工作台体验“换 1 件大一码”，生成预览后先改口，再确认新方案；它只证明应用机制。
自检：为什么 graph ENDED 不代表完成？为什么事实确认不能充当方案批准？为什么“故障已配置”不足以证明恢复成功？
答案分别由 task_state/回执、可信事件绑定及 fault_occurred+同 operation 查询证据支持。

## 下一步边界

business-loop-regression-v4 待批准：原四题各一次，最多 64 请求/160k/1200 秒。
quantity-clarification-regression-v3 待批准：两题各一次，最多 32 请求/64k/600 秒。
精确模型/配置不变，估算和完整 hash 在主报告及计划文件；旧余额不转移、不追加题目。
运行前需新的精确授权和当前账户余量/保护确认；本次未创建新批准文件。
先取得不过度澄清、真实改口、图结束后批准及数量澄清证据，再考虑更广开发集；不运行 holdout 或架构对照。
