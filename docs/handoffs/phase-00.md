# 阶段 0 交接：契约、隔离环境与可运行基础

日期：2026-10-17。项目绝对路径：`/Users/gehanyang/编程/aftercare-agent-workbench`。
本次按最后一条指令只执行阶段 0；未进入阶段 1，不将基础设施交付写成完整工作台。

## 1. 本阶段可以做什么

- 在独立项目 .venv 运行 CLI 和 FastAPI，不需 API Key 或模型权重。
- `/health/live` 直接证明进程能响应；`/health/ready` 真实检查 PostgreSQL、vector 和迁移版本。
- `doctor --offline` 显示配置是否存在、框架版本和数据库状态，不显示 Key/DSN。
- 有界本机数据库探针、专用库迁移入口和 vector baseline migration；拒绝未知库的迁移。
- 显式入口安装非本机网络阻断；阶段 0 的模型客户端工厂无条件拒绝真实模型。
- 完整业务契约/运维/决策/资源清单、四份原设计逐字副本、精确版本与 hash 锁文件、独立 Git 仓库。

业务示例边界：本阶段能显示“服务存活，但售后数据库尚未就绪”；尚不能办理取消/退货/换货。

## 2. 运行与实际验证

所有命令先进入项目：

```bash
cd /Users/gehanyang/编程/aftercare-agent-workbench
.venv/bin/python -m aftercare doctor --offline
.venv/bin/python -m aftercare serve --offline
```

serve 默认 `127.0.0.1:8000`；浏览器访问 `/health/live` 和 `/health/ready`，Ctrl+C 停止。
实际启动检查使用随机本机端口，成功返回 live 200、ready 503，并正常停止进程。

| 验证命令 | 实际结果 | 退出码/证据 |
|---|---|---|
| `.venv/bin/python -m pip check` | 无损坏依赖 | 0；runtime/phase-00/pip-check.log |
| `.venv/bin/python -m ruff check .` | 通过 | 0；runtime/phase-00/ruff-check.log |
| `.venv/bin/python -m ruff format --check .` | 通过 | 0；runtime/phase-00/ruff-format.log |
| `.venv/bin/python -m pytest -m "not live_model and not model_weights" --junitxml=runtime/phase-00/junit.xml` | **12 passed，1 skipped** | 0；runtime/phase-00/pytest.log 与 junit.xml |
| `.venv/bin/python -m aftercare doctor --offline` | DATABASE_UNAVAILABLE，如实未就绪 | **1（预期）**；runtime/phase-00/doctor.log |
| `docker compose config --quiet` | Compose 定义有效 | 0；runtime/phase-00/compose.log |
| `.venv/bin/python -m alembic upgrade head --sql` | 成功生成 baseline SQL（不连接数据库） | 0；runtime/phase-00/migration.sql |
| `.venv/bin/python scripts/verify_phase0.py` | 可执行的阶段 0 检查通过；真实 HTTP 启动验证 | 0；docs/validation-phase-00.json |

汇总 JSON 可跟踪到命令、退出码、输出 hash 和依赖锁 hash。详细原始日志留 runtime，不进 Git。
数据库集成测试跳过原因：未拉取/启动本项目 PostgreSQL，不存在专用已迁移测试库。
离线迁移 SQL 生成成功不代表已经在 PostgreSQL 上执行迁移。
这一跳过不是通过；阶段 1 必须以正式 PostgreSQL 补齐事务和并发验收。

12 项通过覆盖：活性不连接依赖、真实缺库时 503、DSN/Key 脱敏、三类远程数据库地址拒绝、
开关两种状态下真实客户端均拒绝、配置错误不回显、doctor 输出脱敏、外部 DNS/TCP/UDP 阻断、
业务模块/Deep Agents/checkpointer 导入与 app 构建无网络、迁移拒绝未知库。
测试数量不是售后任务成功率；没有运行任何真实售后模型会话。

## 3. 一个完整机制：为何服务活着却未就绪

运行 `serve --offline` → CLI 安装进程网络保护 → Pydantic 读取本项目 .env/环境变量并验证配置 →
构建 FastAPI（此时不连接数据库也不创建模型）→ 本机 HTTP 请求到来。

请求 `/health/live` 时直接返回 alive，不依赖数据库，所以是 200。
请求 `/health/ready` 时进入数据库探针，验证本机地址，在连接/SQL 超时内实际尝试 PostgreSQL；
连接失败只返回 `DATABASE_UNAVAILABLE`，不输出异常中的密码，也不换成 SQLite，所以是 503。
连接成功后还必须有 vector 扩展和 `0001_bootstrap` 迁移版本，才能报告基础设施 ready。
doctor 复用同一探针并以退出码 1 表达缺项；脚本因而可以阻止后续操作。
这条链路完全不需要模型。以后模型只负责决策表达，不能成为数据库是否就绪的裁判。

最多五个核心代码入口：

1. `src/aftercare/cli.py`：doctor/serve/db 命令和离线入口。
2. `src/aftercare/config.py`：配置校验、路径、敏感字段与脱敏摘要。
3. `src/aftercare/api/app.py`：无副作用 app factory、live/ready。
4. `src/aftercare/repositories/database.py`：本机约束、超时、vector 与迁移检查。
5. `src/aftercare/llm/gateway.py`：阶段 0 模型入口无条件拒绝。

后续各组件的位置：服务接收 HTTP；worker 在后台串行执行 Agent；PostgreSQL 保存业务事实、任务、事件与 checkpoint；
LLM 经统一网关提出工具调用。阶段 0 已有服务/数据库接线基础，worker 与 Agent 尚未实现。

## 4. 决定、故障与修复

- 目标原先不存在；两个父目录都不是 Git 仓库，适用路径未发现 AGENTS.md；新建独立仓库，无既有文件覆盖。
- 本机没有 3.12，选已安装 3.13.14，未全局升级。框架版本见 docs/dependency-api.json 和 requirements.lock。
- 检查实际 create_deep_agent、PostgresSaver、interrupt/Command 签名；没有构造远程模型。
- 初始沙箱禁止 Docker socket、依赖 DNS 和本机 bind；通过相同命令在获准权限下重跑确认根因，未通过改应用代码掩盖环境限制。
- 生成锁后再次更新时，pip-tools 7.5.3 在 pip 26.2.1 下导入 `stdlib_pkgs` 失败。原 pip 26.1 下同命令成功，
  因而只在项目内固定 pip 26.1 并重新生成/安装锁。原故障日志为 runtime/phase-00/pip-tools-incompatibility.log。
- SQLAlchemy 对 Linux aarch64 需要 greenlet，本机 arm64 marker 不会自动带入；已显式锁定并检查目标平台 marker 闭包。
  尚未构建容器，marker 检查不等于 Linux 安装验收。
- 设计未固定模拟运费数值，已冻结普通退/换报价 800 分、消费者承担、仅展示不扣款；争议转人工。
- Compose 用专用数据库/卷和本机端口；容器 app 用专用 Unix socket，不给外部网络开例外。
- 静态检查中的格式/导入排序已修正；没有真实业务故障或模型效果可以报告。

## 5. 四种状态与限制

| 状态 | 内容 |
|---|---|
| 已实现 | 阶段 0 CLI、配置、健康接口、离线保护、依赖锁、Compose/Dockerfile、迁移基础、文档 |
| 已验证 | 隔离安装、pip check、实际框架导入/API、静态检查、12 项行为检查、真实 HTTP live/缺库 ready、Compose 配置、四份设计副本一致 |
| 待真实模型验证 | 全部 provider/tool calling/usage/语义理解与成本；阶段 6 前不得调用 |
| 未实现 | 阶段 1—5 业务、检索、Agent、预算、worker、前端、评测；真实 PostgreSQL 迁移运行、并发验收、容器构建验收 |

没有下载镜像/权重，没有启动或修改其他项目的容器，没有真实模型请求，没有公网部署或 GitHub 推送。
Python 离线 audit hook 是进程防误触保护，不声称操作系统级网络隔离。
当前 readiness 仅基础设施；阶段 1 引入迁移后必须跟随新 head 更新检查。

## 6. 用户体验任务与三个问题

体验任务：启动 serve，先访问 live 再访问 ready；在另一个终端运行 doctor，观察退出码与页面状态一致。
无需输入 Key，尚未启动数据库时应看到未就绪。不要为了让检查变绿而去连接其他项目的数据库。

三个理解问题：

1. 为什么 live 可以 200，而 ready 是 503？谁去实际访问数据库？
2. 将 ALLOW_REAL_MODEL_CALLS 改为 true，为何阶段 0 仍不能创建真实模型客户端？
3. 将来服务、worker、数据库、LLM 分别保存或处理什么，为什么不让模型决定数据库事实？

## 7. 下一阶段入口

阶段 1：确定性业务表/迁移、演示数据、预览→可信确认→事务提交→回执；正常与故障 demo，真实 PostgreSQL 并发/回滚验收。
镜像资源已固定清单见 docs/resources.md 与 configs/images.lock.json：PostgreSQL/pgvector ARM64 压缩层约 151 MiB，
Python 基础镜像约 42 MiB；构建还需 Linux Python 依赖。阶段 0 未拉取。

进入阶段 1 时需要用户按阶段 1 指令允许已列明镜像下载；Docker 服务已可用，不需用户安装全局软件。
模型调用仍为禁止；权重下载留到阶段 2 独立列清单。
