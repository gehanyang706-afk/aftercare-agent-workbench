# 售后 Agent 工作台执行约束

目标：实现可恢复、可审计的电商售后多轮决策与执行工作台。
技术栈：Python 3.13、FastAPI、PostgreSQL/pgvector、Deep Agents/LangGraph、原生 HTML/CSS/JS。
业务限于本机单商户模拟订单的查询、取消、退货、换货和转人工；不连接真实支付或物流。

## 目录与命令

- `src/aftercare/`：API/Web、单主 Agent、业务服务、检索、模型预算与 worker。
- `data/`、`configs/`、`migrations/`：模拟数据、版本化政策/配置和数据库迁移。
- `tests/`、`evaluation/`：离线测试、开发场景与独立评分；`runtime/` 保存本机运行资产，不入 Git。
- `docs/`：详细设计、操作说明和 `handoffs/phase-XX.md` 交接记录。

项目根目录运行；先按 `docs/operations.md` 安装项目隔离依赖。

```bash
docker compose up -d db
.venv/bin/python -m aftercare db migrate
.venv/bin/python -m aftercare demo seed --database demo
.venv/bin/python -m aftercare serve --offline
# 另一终端；默认页面 http://127.0.0.1:8000
.venv/bin/python -m aftercare worker --provider scripted
# 专用测试库须先初始化；测试与开发评测不能同时运行
AFTERCARE_TEST_DATABASE_URL=postgresql+psycopg://aftercare:aftercare_local_only@127.0.0.1:55432/aftercare_test .venv/bin/python -m pytest -m 'not live_model'
.venv/bin/python -m evaluation.evaluator.regression_offline --model-mode default
.venv/bin/python -m evaluation.evaluator.regression_offline --model-mode preview-stop
.venv/bin/python -m aftercare eval validate --split dev
.venv/bin/python -m aftercare eval run --split dev --provider scripted
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

当前完成阶段0—5；兼容检查6/6、首轮development-pilot 0/4、闭环v2 2/4、v3 2/4均结案，历史原始记录不改写。
最新同版本互补验证：business-loop-regression-v4为4/4；数量v3仅q1-A尝试且失败，q1-B因硬预算停止未运行。
本轮共39请求、82,027 Token、未知预留0；改口及图结束后应用续跑/事务后丢响应实际覆盖。
q1-A数量猜测被拦，澄清后提交正确，但提交后模型预算拒绝使最终告知缺失；不能称数量组通过。
后续仅做离线通用异常收尾修复：同一批准预览的回执存在才补最终告知，并保留execution_stop停止批次，不重试写入或模型请求。
离线159 passed/0 skipped，针对性7 passed；两种协议替身各六题通过，不回写真实成绩。
最新报告 docs/experiments/complementary-regressions-v1.md，交接 docs/handoffs/phase-06A-complementary-regressions-v1.md。
最新离线数量准备：quantity-evidence-v2支持常见中文件数，process-diagnostic-v5保留无证据参数/预览、拦截及澄清恢复过程缺陷；提示词/冻结评分器/历史场景未改。
最终全量223 passed/0 skipped，新四题两种离线协议各4/4；0新增真实请求，真实数量能力仍待验证。
当前待批quantity-priority-development-v1仅四题，16请求/300秒每题；Token分别48k/40k/40k/48k，全批64请求/176k/1200秒。
逐题cap持久绑定独立账本会话，不能借其他题额度；普通失败继续固定题，安全/协议/usage/预算停止所有后续调用。
旧八题计划已被新scope取代，其他四种表达保留后续开发。新版本与hash见docs/handoffs/phase-06A-quantity-priority-preparation.md。
所有旧真实批次scope均关闭，不能继续q1-B、沿用旧批准或转移余额。未来运行需新hash绑定和当前账户确认。
真实模型仍仅专用源码评测入口注入，普通工作台/worker默认离线。8128仍是19fe7离线镜像，本轮没有重建。
每阶段完成后同步更新本文件中的状态与命令。

## 实现、验收与交接

先读 `docs/design/` 四份设计，以及 `docs/business-contract.md`、`docs/architecture.md`、
`docs/decisions.md` 和最近交接。按阶段顺序实现、验证、必要修复后再推进，不能停在 TODO 或伪实现。
每阶段保存能力、精确运行/验证命令与结果、核心数据流、最多五个代码入口、决定/真实故障、
已实现/已验证/待验证/未实现状态、已知限制、一个完整机制、体验任务与三个问题、下一阶段前置条件。
跳过检查须说明前置条件，目标指标、脚本通过和真实模型效果分别报告。

## 权限、安全与自主执行

- 默认禁止真实模型调用，导入、健康检查和普通测试不能触发外部推理；环境开关不能代替授权。
  获批后严格按精确模型、请求清单、次数、Token/费用/时间上限、停止条件与计划 hash 执行，
  所有调用含重试/用户模拟均走预算网关；usage 不明暂停，不擅自换模型或扩批。
- 只修改本项目；先检查实际目录、适用父目录规则和 Git 状态。不覆盖未知文件、不修改既有项目。
  密钥不入 Git、日志或诊断输出；不自行推送、公开仓库或部署公网，不修改全局配置。
- 不读取独立验收答案调参，不硬编码题目或修改评分提高成绩；已见样本不得称盲测。
- 模型仅表达意图；服务层负责身份、资格、金额、版本、可信确认、幂等及事务提交。
  新消息使旧预览失效；确认绑定对象、参数 hash 与意图版本。事务用 PostgreSQL 验证，不以 SQLite 替代。
- 产品保持单主 Agent、请求与执行双白名单，禁止 shell、任意文件和通用子 Agent 工具。
- 普通实现、项目隔离依赖、测试和修复自主完成。改变范围或增加费用时再确认；
  全局安装、模型权重及大型镜像先列资源清单，已有明确授权范围不重复询问。
  唯一依赖锁为 `requirements.lock`，通过 pip-tools 更新；默认使用 `.venv/bin/python`。
