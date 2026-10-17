# 阶段 4：Web 工作台与恢复体验

已交付三栏页面：对话/澄清、订单/可信确认卡与实际回执、工具/政策/事件时间线。
默认显著标记脚本模拟；身份由 HttpOnly/SameSite 会话注入，写 API 校验 CSRF 与同源。
消息去重与 job 入队同事务；确认与唤醒任务同事务。任务有会话 advisory lock、租约、owner 校验、超时与取消。
SSE 只重放事件；Last-Event-ID 不触发业务或模型。所有展示成功必须有实际 operation 回执。

## 运行命令与实际证据

在项目根目录，本机模式：

```bash
.venv/bin/python -m aftercare db migrate
.venv/bin/python -m aftercare demo seed --database demo
.venv/bin/python -m aftercare serve --offline
# 另一个终端
.venv/bin/python -m aftercare worker --provider scripted
```

默认 127.0.0.1:8000；故障演示需显式 `serve --offline --demo-faults`，普通配置注入 API 返回 404。
容器模式（本轮实际端口 8128，避免占用其他项目端口）：

```bash
docker compose --profile app build app
AFTERCARE_PORT=8128 docker compose --profile app up -d app worker
# 已有初始化；新环境需先 db migrate/demo seed，详情见 operations.md。
```

实际验证：

- `pytest -m 'not live_model'`：**53 passed，0 skipped**，退出码 0，runtime/phase-04/full-tests.log / full-junit.xml。
- 其中 5 项真实子进程 worker 的 E2E：可信确认/消息和确认去重/SSE 重放、改口与跨用户/CSRF、提交后丢响应、租约过期回收/硬截止、运行中取消/进程清理/未知用量。
- ruff check、format、Compose config、容器 pip check、容器 doctor：退出码 0。
- 实际容器通过 HTTP 完成 S1001 取消，重复确认后仍一条操作；docs/experiments/container-smoke.json。
- 容器基础镜像与 PostgreSQL 使用已固定 digest；实际 app image ID 在 runtime/phase-04/image-id.txt。
- 真实浏览器办理 S1002 换大一码→确认→回执；刷新保持同一 operation；新会话退货改为黑色原码后只显示新换货预览；重连回放无重复。
- 浏览器截图：docs/screenshots/workbench.jpg。页面实际操作生成，非静态假图。

## 数据流与完整机制

浏览器带会话 cookie/CSRF → 消息与 job 原子入库 → worker 获取会话锁/租约 → 独立有界子进程执行 Agent →
工具/服务事务 → 业务事件落库 → SSE 增量投递 → 前端按事件 ID 去重并读取快照/回执。

“断线不等于重做”：worker 与 SSE 连接没有执行依赖。断线后任务继续；重连提供事件 cursor，服务器只读既有 events。
刷新从数据库恢复消息、预览和回执。重发消息使用 client_message_id 找回原 job；重复确认使用同 preview 找回原 operation。
三个去重层分别处理消息、事件展示、业务副作用，不能用一个前端按钮 disabled 代替。

五个入口：api/routes.py；workers/worker.py；workers/queue.py；web/static/app.js；web/templates/index.html。

## 真实缺陷与修复

1. 丢响应时数据库已经提交并查回原回执，脚本规划器却优先命中了旧错误分支，误说未执行。
   增加必要告知断言先复现失败，随后把成功回执恢复分支置于旧错误前；lost-before-fix.log 保留失败。
2. Web 过早构建业务连接，导致非法远程 DB 配置让 live/ready 无法启动，阶段 0 回归检出三项失败。
   改为惰性业务工厂；health 仍独立响应/明确拒绝远程 DB，不靠修改原测试跳过问题。
3. 前端并发快照响应可能乱序覆盖新状态，加入请求序号；消息展示按 revision 排序，固定时钟下也保持用户/助手顺序。

## 状态与限制

已实现/已验证：工作台、可信身份/确认、原子入队、租约/会话串行、SSE、刷新/重发/重连、故障恢复、实际容器和浏览器。
待真实模型验证：自由表达理解、真实 provider 协议/usage；所有当前对话是规则脚本模型，真实 API 调用 0。
未实现：完整阶段 5 评测资产与冻结、阶段 6 实际成本/模型对照。
当前仅本机模拟环境，演示身份不是生产认证；日志不展示隐藏推理；单 worker 不承诺生产吞吐。
停止任务不会撤回已提交操作。缺 usage 留预留并暂停模型，用户须查看实际回执；不能把取消等同于未消费/未提交。

体验任务：输入 S1002 退货，等预览后改说“改为换黑色原码”，确认、刷新并比较 operation_id。
三个问题：SSE 为什么不执行 Agent？消息去重与操作幂等为何不同？worker 死亡后租约和 checkpoint 各负责哪一部分？
下一阶段：开发/独立情景、终态+过程+告知评分器、mutation、冻结清单；真实推理仍禁止。
