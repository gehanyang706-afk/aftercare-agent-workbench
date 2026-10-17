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
