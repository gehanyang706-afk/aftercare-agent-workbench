# 阶段 5：评测资产与离线发布候选

完成 schema、60 dev、独立 100 holdout 的公开 manifest、适应式脚本用户、隔离产品子进程、
原始行/过程/告知评分器、6 项 mutation、四配置、JSON/CSV/Markdown 报告、冻结与真实试跑预算。
真实 API 请求始终 0。独立角色获用户明确许可、不继承开发上下文；实现角色未读取答案、未运行 holdout。

## 运行与实际验证

在项目根目录：

```bash
.venv/bin/python -m aftercare eval validate --split dev
.venv/bin/python -m aftercare eval run --split dev --provider scripted --profile full
.venv/bin/python -m aftercare eval verify-grader
.venv/bin/python -m aftercare eval plan --batch compatibility-smoke --dry-run
AFTERCARE_TEST_DATABASE_URL=postgresql+psycopg://aftercare:aftercare_local_only@127.0.0.1:55432/aftercare_test .venv/bin/python -m pytest -m 'not live_model'
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

以上退出码均 0。开发运行只重置 aftercare_test，不能与测试并行；不影响工作台 aftercare_demo。
最终全量 **60 passed，0 skipped，33.34s**；原始日志 runtime/phase-05/full-tests.log、full-junit.xml。
首次因漏设测试库环境变量出现 1 skip，保留 full-tests-missing-env.log；补齐后重跑，未改测试为跳过。

- dev：60 条、60 个单因素家族，四类各 15。首次 53/60，最终 60/60；两份全部结果均保留在 docs/experiments。
- 最终可办理 35/35，应拒绝/不写 25/25；未授权尝试 0/60，错误实际副作用 0/60。
- revision 子集有效订单/意图字段 24/24；只测这两个字段，不称完整长对话约束保持。
- 60 个会话，377 次脚本模型请求；usage 为合成值，未知 0，不能换算真实 Token 或费用。
- 100 条独立集：四类各 25、20 个家族；独立角色报告 schema 全通过。仅公开数量/hash/隔离声明，未声称盲测成功。
- mutation：正确参考通过，错订单、先越权后恢复、重复操作、漏告知、旧批准、错数量全部被识别。
- 四配置均有代码；新增测试验证其他三组也不能用图批准绕过可信 API；未做真实质量/费用对照。
- 新镜像构建、健康、pip check 均通过；应用镜像 952,317,902 字节。基础镜像与权重已固定，当前镜像 ID 见冻结 manifest。
- 浏览器在更新后的 8128 容器办理 S1003 换 41 码，确认产生 op_64d089aeb344400da75d12e351cc33ae；刷新同一回执。
  实际截图 docs/screenshots/workbench-phase05.jpg；旧本机 8127 服务已正常停止，保留容器 app/worker/db。

## 核心数据流与一个完整机制

评测场景 → evaluator 注入时钟/初态 → 脚本用户发一句话 → 独立产品子进程只收会话/消息 →
真实工具/业务事务 → evaluator 读取实际预览后决定改口、拒绝或可信确认 → 原始行/事件导出 →
独立评分器同时检查终态、授权与告知 → 所有题进入分母/报告。
隐藏目标、未来脚本、断言、场景 ID 不传进产品图；故障由 evaluator 在业务事件边界触发，不写进模型上下文。
产品容器不复制 evaluation/runtime，9 项工具不提供任意文件读取。独立集同机保存是工作流隔离，不是密码学保密。

理解“业务正确不等于任务成功”：正常退货必须既有正确 RETURN_REQUESTED 申请，又有匹配可信批准，
并告知尚未退款。只创建正确行但先试图越权，也不通过；后台拒绝越权不能抹掉行为缺陷。
被拒任务则应没有错误操作并给出必要说明；全部转人工会使 35 条可办理题失败。
mutation 构造一份正确参考后只改订单/授权/重复次数/告知，评分必须转为失败。
误执行例来自明确标记的篡改轨迹，不能冒充本轮发生过真实误执行。

五个入口：evaluation/schema/scenario.py；evaluation/evaluator/runner.py；grader.py；
src/aftercare/agent/workflow.py（其余组在 runtime/middleware）；evaluation/manifests/release-candidate.json。

## 本轮实际故障与决定

1. 用户要求两件但脚本默认一件，脚本用户拒绝确认，d-013/d-025 失败。添加通用数量解析并保存有效约束；没按题号分支。
2. 提交前异常正确回滚，但工具直接抛出令图退出。统一未知写入错误，先查原回执；未查到则明确不能宣称成功，禁止盲重写。
3. dev v1 两条告知标签写成不存在的 ORDER_STATE，终态/过程均已正确。单独 v2 修正为实际协议 INELIGIBLE_STATUS，
   不改资格或评分函数；数据修正不能算产品进步，完整修订记录见 development-data-revisions.md。
4. 完整政策基线使用实际 full-policy、完整历史；retrieval 用 BM25/完整历史；full 另用有效状态/四块历史与有界读恢复。
   fixed-workflow 经固定阶段门，同一离线意图模型。正式两组候选为 react-full-policy/full，尚待真实开发试跑验证价值。

## 四种状态与限制

已实现：阶段 0—5 本机工程、场景/评分/报告/冻结、实际工作台。
已验证：PostgreSQL 60 项离线测试、60 条已见开发任务、mutation、容器与真实浏览器。
待真实模型验证：provider 帐号/区域/模型兼容性、自由表达、usage/成本、正式对照、长对话和重复稳定性。
未实现/未授权：阶段 6 实际发送与正式实验、阶段 7 干净机交付/面试材料；当前 provider 执行仍硬拒绝。

告知检查为字面替代词，不是完整语义裁判；oracle 为公开有限键，不接受未知断言。
开发通过不是独立成功率，377 次合成调用不是付费调用。分段延迟和重复稳定性未测，报告保留 null。
独立数据未人工抽审；后续需独立角色审计，不能由实现者读答案调参。holdout 在 runtime，不入 Git，应本机备份。

体验任务：阅读 development-final.json 中一条正常办理和一条拒绝，再运行 verify-grader 看错订单如何被判失败。
三个问题：为何业务回滚仍可能算任务失败？为何拒绝预览不是聊天“好的”？为何最终正确不能掩盖先前越权？

## 阶段 6 前置与待批准计划

计划：evaluation/manifests/compatibility-smoke.json；模型 qwen3.5-plus-2026-02-15，关闭思考，并发 1。
6 项：普通文字、工具调用、工具结果、流式 usage、可校验 JSON、严格工具 schema。
加 2 个重试槽后最多 8 次 HTTP、20,000 总 Token；单请求保守上限 1,821、输出最多 128；最长 600 秒，单请求 60 秒。
序列化 dry-run 保守预留合计 12,600；预留不是实际用量。包含重试，无 SDK 隐式重试。
认证/模型/区域/额度异常、协议不兼容、usage 不明或断流、任何上限/取消均停止，不换模型/扩批。
默认不授权额外付费。用户须在账户启用免费额度保护且确认计划 hash 后，才进入真实调用实现与执行。
仅批准这一小批不等于批准 development-pilot 或 holdout 对照；Key 不在聊天提供。
