# 环境、运行与排障

本机已安装 /opt/homebrew/bin/python3.13（3.13.14）；所有项目命令使用 .venv。
不需要 Node，不需要全局安装软件。阶段 0 不依赖模型 Key 或权重。

## 从锁文件重建

下面用于新副本/新环境，不能覆盖正在使用的其他项目环境：

```bash
cd /Users/gehanyang/编程/aftercare-agent-workbench
/opt/homebrew/bin/python3.13 -m venv .venv
.venv/bin/python -m pip install --cache-dir runtime/pip-cache --require-hashes -r requirements.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
.venv/bin/python -m pip check
```

重新解析锁文件仅在有依赖变更时运行；更新后重新验证并记录版本：

```bash
.venv/bin/pip-compile --extra dev --all-build-deps --allow-unsafe --generate-hashes --strip-extras --output-file requirements.lock --cache-dir runtime/pip-cache pyproject.toml
```

.env 可由 .env.example 复制，只作用于本项目。无需配置真实 Key；不要把 Key 发到聊天。
doctor 只显示 Key/Base URL 是否设置，不显示值；错误输出不回显 DSN 或配置原文。

## 当前可运行命令

```bash
.venv/bin/python -m aftercare doctor --offline
.venv/bin/python -m aftercare serve --offline
.venv/bin/python -m aftercare db current
.venv/bin/python -m aftercare db migrate
```

serve 默认 127.0.0.1:8000；--port 可调整冲突端口。--container-network 仅用于容器内部监听，
Compose 的宿主映射固定 127.0.0.1。禁止直接将工作台公开到公网。
doctor：0 基础设施 ready；1 依赖未就绪；2 配置无效。db：未知库拒绝退出 2；连接/迁移失败退出 1。

ready 在 2 秒连接超时和 2 秒 SQL 超时内检查数据库、vector 和当前 Alembic revision。
它不调用模型、不写表、不自动修复。可能返回 DATABASE_UNAVAILABLE、PGVECTOR_MISSING、
MIGRATIONS_REQUIRED、SCHEMA_REVISION_MISMATCH、OFFLINE_DATABASE_HOST_DENIED。
live 只证明服务进程响应；ready scope=phase-0-infrastructure 也不证明售后链路已完成。

## 专用数据库（授权镜像下载后再运行）

阶段 0 仅验证 Compose 定义，尚未执行以下拉取/启动操作。资源见 resources.md；
用户按阶段 1 指令明确允许已列明基础镜像后，不必逐条重问。

```bash
docker compose up -d db
.venv/bin/python -m aftercare db migrate
.venv/bin/python -m aftercare db current
.venv/bin/python -m aftercare doctor --offline
```

独立项目名 aftercare-agent-workbench，库 aftercare_demo，角色 aftercare，密码为公开的本机模拟密码，
端口 127.0.0.1:55432。卷仅属于此 Compose 项目，不复用其他项目。不要连接真实数据库。
db migrate 只允许本机 aftercare_demo 或 aftercare_test；没有清库/重置命令。

阶段 1 增加专用测试库和事务验收。当前如已自行准备 aftercare_test 并迁移，可显式启用真实探针测试：

```bash
DATABASE_URL=postgresql+psycopg://aftercare:aftercare_local_only@127.0.0.1:55432/aftercare_test .venv/bin/python -m aftercare db migrate
AFTERCARE_TEST_DATABASE_URL=postgresql+psycopg://aftercare:aftercare_local_only@127.0.0.1:55432/aftercare_test .venv/bin/python -m pytest tests/integration
```

## 容器应用（同样需要镜像/构建下载授权）

```bash
docker compose --profile app build app
docker compose up -d db
docker compose --profile app run --rm app python -m aftercare db migrate
docker compose --profile app up -d app
```

容器通过共享专用 PostgreSQL Unix socket 连接数据库，以保持严格非本机网络阻断；宿主开发使用 TCP。
没有为 Docker 网络域名添加外部网络例外。socket 卷 app 只读挂载，不包含数据库数据文件。
不把 .env/模型 Key/评测答案/原始运行日志打进镜像。
worker 尚未实现，因此不创建假 worker 服务；阶段 4 将加入可实际领取任务的入口。

暂停使用 `docker compose --profile app stop`；保留数据停止用 `docker compose --profile app down`。
不使用 down -v，它会删除项目数据卷。阶段 0 未启动容器，因此没有需要清理的运行服务。

## 验证与证据

```bash
.venv/bin/python -m pytest -m "not live_model and not model_weights"
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
docker compose config --quiet
```

runtime/phase-00 保存本机详细日志（被 Git 忽略）；可跟踪验收摘要在 docs/validation-phase-00.json。
离线保护覆盖 Python socket/DNS/UDP，不是 OS 沙箱；当前不暴露 subprocess 推理路径。
依赖下载不等于模型推理；没有安装 torch、sentence-transformers 或模型权重。
