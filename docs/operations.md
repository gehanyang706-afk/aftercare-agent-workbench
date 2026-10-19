# 当前候选版启动与维护

项目根目录：/Users/gehanyang/编程/aftercare-agent-workbench。当前已进入收尾候选，最后六题真实验收待批准；版本/镜像/证据以evaluation/manifests/closing-candidate-v1.json为准，health里的历史phase标签不是发布版本。

## 已验证的离线工作台

本机 http://127.0.0.1:8128，app/worker已更新到closing-offline-rc1。无须Key；默认ScriptedModel+BM25，页面明确标注脚本模拟。真实账本与演示业务在aftercare_demo，普通界面不能切换真实provider。

```bash
cd /Users/gehanyang/编程/aftercare-agent-workbench
docker compose up -d db
AFTERCARE_PORT=8128 docker compose --profile app up -d --no-build --no-deps app worker
# 暂停应用；数据库与数据保留
docker compose --profile app stop app worker
```

不要执行down -v、demo reset、删预算表或batch-state。现库含真实账本，reset已返回REAL_LEDGER_RESET_FORBIDDEN；新建会话即可保留历史。订单、占用和库存会影响演示，如条件不满足应展示拒绝，不擅自重置。

## 源码启动（和容器二选一）

使用现有Python3.13和项目.venv。先停容器app/worker，避免多个worker和演示状态混淆。

```bash
.venv/bin/python -m aftercare db migrate
.venv/bin/python -m aftercare demo seed --database demo
.venv/bin/python -m aftercare doctor --offline
.venv/bin/python -m aftercare serve --offline --port 8128
# 另一终端，在同项目目录
.venv/bin/python -m aftercare worker --provider scripted
```

seed幂等，不覆盖旧数据。serve/worker各Ctrl+C停止。doctor检查本地PG/vector/Alembic，不发送模型请求。Key/Base URL只显示是否存在，不输出.env。

## 无网络重建与回滚

本轮仅使用已缓存依赖与基础镜像，没有拉取大型镜像或安装全局软件。

```bash
docker build --network=none --pull=false -f Dockerfile.offline-update -t aftercare-agent-workbench:closing-offline-rc1 .
docker image tag aftercare-agent-workbench:closing-offline-rc1 aftercare-agent-workbench:local
AFTERCARE_PORT=8128 docker compose --profile app up -d --no-build --no-deps app worker
# 回滚应用镜像；数据不回滚
docker image tag aftercare-agent-workbench:before-final-acceptance aftercare-agent-workbench:local
AFTERCARE_PORT=8128 docker compose --profile app up -d --no-build --no-deps app worker
```

旧镜像只用于应用回滚，不代表包含新暂停/来源修复。开始前必须无RUNNING/PENDING任务；不得在真实验收中重建或换源码。数据备份与恢复需另行明确操作，不提供删除真实账本的捷径。

## 离线验证

```bash
AFTERCARE_TEST_DATABASE_URL=postgresql+psycopg://aftercare:aftercare_local_only@127.0.0.1:55432/aftercare_test ALLOW_REAL_MODEL_CALLS=false .venv/bin/python -m pytest -m 'not live_model'
ALLOW_REAL_MODEL_CALLS=false .venv/bin/python -m evaluation.evaluator.regression_offline --scenario-file evaluation/dev/final-acceptance-v1.jsonl --user-policy-version script-user-v3 --model-mode default
ALLOW_REAL_MODEL_CALLS=false .venv/bin/python -m evaluation.evaluator.regression_offline --scenario-file evaluation/dev/final-acceptance-v1.jsonl --user-policy-version script-user-v3 --model-mode preview-stop
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

三项PG验证串行执行，都重置aftercare_test，禁止和真实评测/其他pytest同时运行。全量237通过/0跳过；最后六题两种脚本模式各5/6，fa1-03“大一号”为已知替身解析限制，被后端拒绝。历史开发100题离线结果和真实模型成绩不是同一口径。
依赖安装、锁和模型资产见requirements.lock、configs/local-models.lock.json及此前阶段交接；本次不需要下载或更新模型权重。

## 最后真实验收与收尾

只接受final-development-acceptance-v1具体hash的新批准+执行前当前免费余量/北京/FreeTierOnly确认。计划本身不授权，旧批准/余量不继承。专用源码CLI运行，普通Web/worker继续离线；只清aftercare_test，真实BudgetLedger保留aftercare_demo。
完整六题/上限/停止条件/收尾规则见docs/closing/final-acceptance.md。批中冻结；普通失败保留继续，安全/协议/usage/硬预算异常停。验收后除阻断问题不自动追加回归或调提示词。
启动验证记录、镜像身份和真实账本不变证据见closing-candidate-v1.json。五分钟演示、结果总表及面试讲解分别见docs/closing/demo-script.md、results-summary.md、interview-handoff.md。
