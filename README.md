# 电商售后多轮决策与执行 Agent 工作台

已完成阶段 0—5：可运行三栏工作台、单主 Agent 工具循环、可信确认、真实 PostgreSQL 原子提交、幂等恢复、政策检索与任务队列。
普通界面默认是明确标记的**脚本模拟模式**；专用入口的真实开发回归结果按版本单列，不代表生产成功率。

![工作台实际浏览器截图](docs/screenshots/workbench-phase05.jpg)

## 运行

```bash
cd /Users/gehanyang/编程/aftercare-agent-workbench
docker compose up -d db
.venv/bin/python -m aftercare db migrate
.venv/bin/python -m aftercare demo seed --database demo
.venv/bin/python -m aftercare serve --offline
# 第二终端
.venv/bin/python -m aftercare worker --provider scripted
```

打开 http://127.0.0.1:8000。当前已启动的容器工作台在 http://127.0.0.1:8128。
可体验“S1002 换大一码”、确认前改口、刷新/重连。取消只记录模拟退款请求，退换仅提交申请，不声称到账或寄出。

[操作说明](docs/operations.md)提供 Docker、重置、故障演示、依赖重建与验证命令。
[业务契约](docs/business-contract.md)、[架构](docs/architecture.md)、[决策](docs/decisions.md)、
[资源清单](docs/resources.md)、[阶段交接](docs/handoffs/)保留实现与验证边界。

阶段 0—5 禁止真实模型调用；阶段 6 必须另行批准精确模型、场景、请求数、Token 上限与停止条件。
阶段 5 已交付 60 条开发场景、100 条独立验收场景的公开 manifest、独立评分器和冻结清单。
独立答案未由实现角色读取或运行；开发脚本通过不代表真实模型成功率。

```bash
.venv/bin/python -m aftercare eval validate --split dev
.venv/bin/python -m aftercare eval run --split dev --provider scripted
.venv/bin/python -m aftercare eval verify-grader
.venv/bin/python -m aftercare eval plan --batch compatibility-smoke --dry-run
```

[评测说明](evaluation/README.md) · [开发结果](docs/experiments/development-final.md) ·
[阶段 5 交接](docs/handoffs/phase-05.md) · [真实试跑待批计划](evaluation/manifests/compatibility-smoke.json)


阶段 6A compatibility-smoke 已完成：精确模型 qwen3.5-plus-2026-02-15，6/6 协议检查通过，
6 次真实请求、0 重试，输入 1,001 / 输出 101 Token，未知预留 0，耗时 13.933 秒。
这不等于真实售后 Agent 评测；当前工作台仍为脚本模拟。
[实际兼容报告](docs/experiments/compatibility-smoke.md) ·
[6A 交接](docs/handoffs/phase-06A-compatibility-smoke.md) ·
[下一批待批计划](evaluation/manifests/development-pilot.json)。


阶段 6A 首轮 development-pilot 已结案，**0/4 任务完成**；24 次真实请求，输入 48,040 / 输出 1,831，
未知预留 0。没有实际业务操作；一次工具顺序错误，三题涉及数量歧义与脚本用户缺口。
改口及丢响应恢复未触发，不声称真实闭环通过。首轮证据不重写；后续真实批次按版本单列。
[首轮结果与归因](docs/experiments/development-pilot-first.md) ·
[交接记录](docs/handoffs/phase-06A-development-pilot.md) ·
[新回归草案，未批准](evaluation/manifests/development-pilot-regression-01.json)。


此前真实开发回归 business-loop-regression-v3：**2/4**，19 请求、输入 35,392 / 输出 1,141 Token，未知预留 0。
取消及事务后丢响应恢复通过；换码/改口停在重复澄清，改口未覆盖。
第二批数量澄清因门禁失败未运行。历史 0/4、v2 2/4 均保留，不计算跨版本提升。
批次结束后仅完成通用提示词候选和旁路诊断调整；离线两种模式各六题通过不代表真实失败已解决。
[本批逐题结果、预算与新待批计划](docs/experiments/business-loop-regression-v3-first.md) ·
[交接](docs/handoffs/phase-06A-business-loop-regression-v3.md)。
普通工作台真实入口保持关闭；本轮源码候选未更新到 8128 旧离线镜像。


最新同版本互补验证：**业务闭环 v4 4/4；数量组 v3 的 q1-A 失败、q1-B 因预算停止未运行**。
合计39请求、输入79,324 / 输出2,703 Token、未知预留0。改口和事务后丢响应实际触发；丢响应走图结束后的应用续跑。
q1-A猜数量的预览被拦；用户明确1件后实际提交，但提交后模型预算拒绝造成最终告知缺失。
原始结果保持不变；后续离线修复保留预算停止信号，并从原回执完成告知，不补发模型请求。
[逐题结果、归因与八题多样表达待批计划](docs/experiments/complementary-regressions-v1.md)。
新八题仅手工准备和静态校验，尚未授权或执行；普通工作台仍默认离线。


当前下一批已缩为四题数量优先验证（换货澄清1件、退货澄清2件、明确2件缺货、澄清2件后缺货），旧八题计划被取代，未授权真实执行。
常见中文件数、参数级过程诊断及提交后停止的回执告知已完成离线准备，223项测试通过；不代表新的真实效果成绩。
[简短交接与待批预算/hash](docs/handoffs/phase-06A-quantity-priority-preparation.md) ·
[四题冻结计划](evaluation/manifests/quantity-priority-development-v1.json)。
