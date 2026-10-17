# 阶段 1：确定性业务与原子提交

本阶段已实现并在真实 PostgreSQL 验证；无真实模型调用。授权依据：用户“可下载资源，继续工作”。

## 可用能力、运行与证据

查询当前用户订单/库存；取消整单、退货和换货申请；预览去重、可信确认、幂等提交/回执；人工工单。
模拟后台可以发货，以及拒绝、撤回、完成申请；库存预留相应释放或消耗，重复处理无重复释放。
数据库表有数量、库存非负和唯一操作约束，事务中按会话→订单→商品行→库存加锁。

在 `/Users/gehanyang/编程/aftercare-agent-workbench` 运行：

```bash
docker compose up -d db
.venv/bin/python -m aftercare db migrate
.venv/bin/python -m aftercare demo seed --database demo
.venv/bin/python -m aftercare demo run --case normal-exchange
# 每个演示之间显式恢复本项目演示初态；会清除本项目演示业务数据。
.venv/bin/python -m aftercare demo reset --confirm demo-only
.venv/bin/python -m aftercare demo run --case lost-submit-response
.venv/bin/python -m aftercare demo reset --confirm demo-only
.venv/bin/python -m aftercare demo run --case concurrent-stock
.venv/bin/python -m aftercare demo reset --confirm demo-only
.venv/bin/python -m aftercare demo run --case revise-before-confirm
AFTERCARE_TEST_DATABASE_URL=postgresql+psycopg://aftercare:aftercare_local_only@127.0.0.1:55432/aftercare_test .venv/bin/python -m pytest tests/unit tests/integration
```

最后一条实测 **30 passed，0 skipped**，退出码 0，`runtime/phase-01/tests.log` 与 junit.xml。
静态检查/格式检查退出码 0。迁移、doctor、正常换货演示退出码均 0；数据库 ready。
其余演示真实输出在 runtime/phase-01/{lost-response,concurrent,revision}.json：并发仅一笔提交，
另一笔 STATE_CHANGED；改口后旧确认 PREVIEW_INVALIDATED；丢响应后按原 preview 找回同一回执。
镜像精确 digest 沿用 configs/images.lock.json；实际容器镜像记录 runtime/phase-01/images.json。
开发测试仅重置 aftercare_test，演示重置要求显式 demo-only、专用角色/库名/项目 schema；不连接其他项目。

## 完整数据流与一个机制

ActionInput 参数校验 → 服务端 principal 过滤订单 → 确定性资格与政策版本 → 只读预览（600 秒）→
可信 API/service confirm 记录绑定 hash/revision 的 Approval → commit 锁住会话、订单行、库存 →
重新校验版本/资格 → 一个事务写申请、库存预留、operation、幂等键映射、业务事件 → 返回回执。

“提交成功但响应丢失”机制：事务已提交后才注入丢响应异常；operation/申请已在库里。
重启服务或重复点击都先读取已存在的 preview 唯一 operation；换 key 也返回同一回执，所有使用过的 key
均绑定 request hash，之后不能拿同 key 办另一笔。checkpoint 尚未接入；幂等性已由数据库独立保证。

五个入口：services/business.py；domain/rules.py；repositories/models.py；
services/demo.py；migrations/versions/0002_business.py（DDL 已冻结，不随未来 ORM 漂移）。

## 决定、真实缺陷与修复

确认和提交都重新检查订单版本。两条先失败后修复的回归测试证明：旧代码会复用过期预览、确认发货后旧版本；
修复为只复用仍有效的预览，并在确认时锁订单复核版本。日志 regression-before-fix.log 保留两项失败。
预览唯一约束只覆盖活动状态，允许到期后重新生成；活跃请求数量由行锁与数据库 check 双重保护。
所有金额为整数分，7/15×24 小时的含边界与超出 1 微秒均实测；取消只创建模拟退款请求，退换仅为申请。

## 状态与限制

已实现：上述业务服务、真实数据库迁移、三位用户七笔订单、演示/测试故障入口。
已验证：30 项测试，包括两客户竞争最后库存、同预览并发重复提交、重叠数量、共同回滚、库存释放、越权和政策变化。
待真实模型验证：所有语义理解，阶段 6 前不调用。
未实现：检索、Agent/HITL、预算、Web/worker/SSE、评测。服务层可用，HTTP 业务入口留阶段 4。

体验任务：依次演示换货、重复提交和丢响应恢复，比较 operation_id 与数据库库存。
三个问题：为什么预览不长期占库存？为什么换 key 不能多办一次？为什么成功提交后改口不能宣称回滚？
下一阶段：政策语料/BM25/向量接口和有效诉求状态；先核实本地模型 revision/大小，资源授权已取得，不重复询问清单内下载。
