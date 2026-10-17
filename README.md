# 电商售后多轮决策与执行 Agent 工作台

当前交付 **阶段 0**：隔离依赖、冻结契约、离线 CLI、可运行健康接口和 PostgreSQL 迁移基础。
尚未实现订单办理、Agent、前端工作台与评测；没有真实模型效果或业务成功率。

## 本机运行

```bash
cd /Users/gehanyang/编程/aftercare-agent-workbench
.venv/bin/python -m aftercare doctor --offline
.venv/bin/python -m aftercare serve --offline
```

浏览器访问 [活性](http://127.0.0.1:8000/health/live) 与
[基础设施就绪](http://127.0.0.1:8000/health/ready)。没有数据库时 live 为 200，ready 为 503，doctor 退出 1，
属于如实报告依赖缺项。Ctrl+C 停止服务。不需要填写 API Key。

```bash
.venv/bin/python -m pytest -m "not live_model and not model_weights"
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
```

普通测试默认禁止外部网络；真实数据库测试必须显式配置 AFTERCARE_TEST_DATABASE_URL，缺失会报告 skip。
全部 CLI 默认离线，模型客户端工厂在阶段 0 无条件拒绝真实模型；环境变量开关不能越过阶段边界。

## 继续阅读

- [阶段 0 实际交接](docs/handoffs/phase-00.md)：验收、数据流、入口、限制和体验任务。
- [业务契约](docs/business-contract.md)、[架构](docs/architecture.md)、[决策](docs/decisions.md)。
- [操作说明](docs/operations.md)：按锁重建、数据库/容器命令、退出码与排障。
- [资源清单](docs/resources.md)：现有环境、待授权镜像、后续权重边界。
- 原设计四份副本在 docs/design，源文件保持不变；来源 hash 见 docs/design-manifest.json。

只面向本机模拟业务。阶段 0 不需要运行额外模型进程或后台 worker。
