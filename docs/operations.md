# 操作说明

项目根目录 `/Users/gehanyang/编程/aftercare-agent-workbench`。使用现有 Python 3.13.14 和项目 .venv。

## 本机启动

```bash
docker compose up -d db
.venv/bin/python -m aftercare db migrate
.venv/bin/python -m aftercare demo seed --database demo
.venv/bin/python -m aftercare doctor --offline
.venv/bin/python -m aftercare serve --offline
# 第二终端
.venv/bin/python -m aftercare worker --provider scripted
```

打开 http://127.0.0.1:8000，选择客户进入工作台。无须配置 Key。
若端口占用用 `serve --offline --port 8127`。Ctrl+C 停止对应进程，数据库另由 Compose 管理。

## 容器启动

```bash
docker compose --profile app build app
docker compose up -d db
docker compose --profile app run --rm app python -m aftercare db migrate
docker compose --profile app run --rm app python -m aftercare demo seed --database demo
AFTERCARE_PORT=8128 docker compose --profile app up -d app worker
```

打开 http://127.0.0.1:8128。本轮实际容器运行在此端口。app 和 worker 用专用 Unix socket 连接 PostgreSQL。
镜像不含 Key、权重、评测答案或原始日志；默认只运行脚本模型+BM25。宿主机可另跑已验证的 ONNX 检索对照。
暂停：`docker compose --profile app stop app worker`；保留数据关闭：`docker compose --profile app down`。
不要使用 down -v，它会删除专用数据卷。勿同时启动多个无必要的本机/容器 worker。

## 重置、故障与排障

`demo seed` 不覆盖已有数据，若交付时间太久导致演示订单超时，先停止/完成活动 job，然后显式运行：

```bash
.venv/bin/python -m aftercare demo reset --confirm demo-only
```

仅清除本项目 aftercare_demo 的已知业务表并重建模拟初态；拒绝未知库/角色/schema 或存在活动任务。
不会自动清理其他数据库，不提供生产数据重置。aftercare_test 专用于测试，测试会重置其中 fixture，勿保存业务数据。

`serve --offline --demo-faults` 开启本机演示注入：下次提交后丢响应、下次任务阻塞、下次提交前回滚。
普通运行默认关闭该接口。阻塞任务可点停止；未知用量保留预算，演示可在没有活动 job 后显式重置。
确认前说新诉求会使旧方案失效；不要把聊天“好的”当授权。提交后改口不会撤回已有申请。

live 200 仅表示进程响应；ready 检查数据库、vector 与当前 Alembic head，失败 503；doctor 对应退出 1。
配置错误退出 2。Key/Base URL 只报告是否存在；异常不回显 DSN。全局 ALLOW_REAL_MODEL_CALLS 仍不能开启真实调用。

## 依赖与验证

```bash
/opt/homebrew/bin/python3.13 -m venv .venv
.venv/bin/python -m pip install --cache-dir runtime/pip-cache --require-hashes -r requirements.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
.venv/bin/python -m pip check
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
AFTERCARE_TEST_DATABASE_URL=postgresql+psycopg://aftercare:aftercare_local_only@127.0.0.1:55432/aftercare_test .venv/bin/python -m pytest -m 'not live_model'
```

缺少测试库时先在本项目 PostgreSQL 创建 aftercare_test，再用 DATABASE_URL 指定该库运行 db migrate。
真实事务不用 SQLite；普通 pytest 禁止外部网络。模型权重已在 runtime/models，固定 revision/hash 见 configs/local-models.lock.json。
重新取得权重运行 scripts/download_models.py；embedding 导出运行 scripts/export_embedding.py。均不得改全局缓存。
锁更新：`pip-compile --extra dev --all-build-deps --allow-unsafe --generate-hashes --strip-extras --output-file requirements.lock --cache-dir runtime/pip-cache pyproject.toml`，仅依赖变化时使用。
Python 离线 hook 不是 OS 沙箱；本项目不暴露 shell/任意文件工具，LLM 工厂和 provider 执行仍拒绝真实请求。

## 离线评测与真实试跑边界

```bash
.venv/bin/python -m aftercare eval validate --split dev
.venv/bin/python -m aftercare eval run --split dev --provider scripted --profile full
.venv/bin/python -m aftercare eval verify-grader
.venv/bin/python -m aftercare eval plan --batch compatibility-smoke --dry-run
```

dev 运行会重置专用 aftercare_test，逐题导出再重置，不触碰 aftercare_demo；不要与 pytest 并行。
运行输出 runtime/phase-05/dev-*/report.{json,csv,md}。阶段 5 正式保存的开发报告在 docs/experiments/development-final.*。
详细隔离、分母和局限见 evaluation/README.md。独立答案不进 Git，请自行备份整个项目 runtime/independent-evaluator 目录。
通用真实 Agent 调用仍被阻止；专用 compatibility-smoke 入口已完成一次获批执行，不能重复启动同批次。
仅该入口支持临时 ALLOW_REAL_MODEL_CALLS=true，并同时校验具体计划 hash、审批、账户确认与预算。
实际报告见 docs/experiments/compatibility-smoke.md；development-pilot 需独立批准，不能继承本批剩余额度。
不要在聊天里发送 Key。真实联调前应在账户侧启用仅免费额度保护；任何额外付费需单独批准。


首轮 development-pilot 已执行并关闭，入口为 `model smoke --batch development-pilot`，绑定其审批/账户确认。
不要直接再次执行；持久状态与账本会拒绝复跑。详情见 docs/handoffs/phase-06A-development-pilot.md。
真实业务适配通过受限模型注入，普通 Web/worker 仍为脚本模式，不因 .env 开关自行更换 provider。
业务 fixture 与真实 ledger 分库；真实批次运行期间仍不得并行 pytest 或离线 dev 清库。
原始状态/事件/请求/响应保存在 runtime/development-pilot-first，批次后离线测试不覆盖这些证据。
新候选数据与回归计划是独立版本，尚未授权；旧批剩余额度不能当作新批许可。

## 闭环修复与数量澄清的离线回归

项目根目录运行：

    .venv/bin/python -m evaluation.evaluator.regression_offline

仅加载 regression-v1 四题和 quantity-clarification-v1 两题，scripted/full、产品子进程强制离线，
只重置 aftercare_test；不能与 pytest 并行。输出在 runtime/closure-repair/offline-时间戳。
118 项离线测试和最终六题记录见 docs/experiments/business-loop-repair.md。
现有常驻旧容器本次未重建；用源码启动或依照上文重新构建才能体验新代码。

专用 model smoke 增加 business-loop-regression-v2 与 quantity-clarification-regression-v1 两个命名范围；
只接受新计划 hash、固定源码、独立人工审批、当前免费余量/北京地域/FreeTierOnly 确认，
并临时启用真实进程开关。计划本身不构成批准，本次没有新真实调用。
完整上限/重试/停止条件在各 evaluation/manifests 同名计划；不得沿用旧 pilot 审批。

## business-loop-regression-v2 已执行结案

首次真实批次 2/4，28 请求/54,787 Token/152.835 秒；完整逐题证据见
docs/experiments/business-loop-regression-v2-first.md。
批次状态 COMPLETED 表示四题全部尝试，不代表四题通过；禁止直接重复上述历史执行命令。
现有启动保护同时检查持久账本及 batch-state.json，不能删除状态绕过。

源码/环境保持冻结版本；无 pending graph task 的可信确认续跑尚未修复。
quantity-clarification-regression-v1 仍未授权/未执行，新真实回归均须新明确批准。
先离线解决确认续跑缺口，再冻结下一批版本；本批余量不转移。

## 可信确认续跑修复版（当前本机工作台）

http://127.0.0.1:8128 的 app/worker 已更新到工程提交 19fe7ad；
真实开关仍关闭，演示订单/库存/真实账本保持原样。
完整验证与版本指纹见 docs/experiments/confirmation-continuation.md；
新方案包含绑定确认事件、图结束后续跑、回执型最终告知与独立任务状态。

运行两种离线协议回归：

    .venv/bin/python -m evaluation.evaluator.regression_offline --model-mode default
    .venv/bin/python -m evaluation.evaluator.regression_offline --model-mode preview-stop

仅使用 aftercare_test 和 ScriptedModel，不运行真实批次或 holdout。
不能与 pytest/其他评测并行重置测试库。
无完整绑定事件的旧确认任务安全拒绝，不能只凭旧 CONFIRMED 状态继续写入。

已有本地项目镜像时，可无网络叠加源码：

    docker build --network=none --pull=false -f Dockerfile.offline-update -t aftercare-agent-workbench:confirmation-offline .

该方式不安装依赖；前提是当前项目镜像的 requirements.lock 与源码一致。
更新前须确认本项目没有正在执行的任务并保留旧镜像，本次回滚镜像名为
aftercare-agent-workbench:before-confirmation-continuation，不覆盖该备份。

新版 app/worker 已核对源码 hash 与真实开关；当前 health 的 phase-4-infrastructure
是历史基础设施标签，版本应以冻结清单、镜像 ID 与源码 hash 为准。

当前专用待批入口为 business-loop-regression-v3 和 quantity-clarification-regression-v2，
分别需新审批/当前账户确认及新 hash，普通工作台不切换真实模式。
旧 business-loop-regression-v2、quantity-clarification-regression-v1 在入口明确拒绝。
不得直接复用历史审批或为了“再次验证”启动旧真实批次。
