# 决策记录

## D001：保留已安装 Python 3.13.14

实际本机只有 3.13.14、3.14，未发现 3.12。任务书允许阶段 0 诊断后锁定明确版本。
选择 3.13.14，requires-python 限于 3.13，.python-version 锁补丁；不用全局安装解决。
容器同样使用 3.13.14。依赖兼容性由解析、pip check、实际导入和 API 检查验证。

## D002：pip-tools + 一个 requirements.lock

依赖范围在 pyproject.toml；含 dev 的传递依赖、精确版本和发行包 hash 统一锁定。
安装先 --require-hashes，再 --no-deps 安装本项目。平台包按锁定 hash 选择适合 ARM64/Linux 的发行文件。
不同时引入 uv.lock。安装解析不等于业务语义验证。
SQLAlchemy 的 greenlet 依赖在 macOS arm64 和 Linux aarch64 上具有不同 marker；
检查发行包元数据后显式纳入 greenlet，避免本机生成的锁文件遗漏容器必需依赖。
这仍不代替真实容器构建验收；阶段 0 只核查目标平台的依赖 marker 闭包。
实际遇到 pip-tools 7.5.3 配合 pip 26.2.1 重新解析时导入 stdlib_pkgs 失败；
固定已成功运行同命令的 pip 26.1，在新项目 .venv 内修复，不修改全局 pip。

## D003：实际框架 API 作准

Deep Agents 固定 0.7.28，LangGraph、checkpoint-postgres、psycopg 等兼容解析结果见 requirements.lock。
官方包声明 Python >=3.11；本次检查已安装 create_deep_agent 签名与 PostgresSaver，不构造远程模型。
阶段 3 必须重新核对默认工具及 middleware，不把阶段 0 的导入成功当完整 Agent 验收。
参考：[Deep Agents PyPI](https://pypi.org/project/deepagents/)、
[官方自定义](https://docs.langchain.com/oss/python/deepagents/customization)、
[持久化](https://docs.langchain.com/oss/python/langgraph/persistence)。
实际签名、包依赖声明和源码位置保存在 docs/dependency-api.json。

## D004：未就绪显式失败

live 表示进程能响应；ready 必须连上数据库且有 vector 和当前迁移版本。
doctor 未就绪退出 1、配置错误退出 2、完全就绪退出 0。没有数据库不降级成内存或 SQLite。
阶段 0 的就绪范围仅基础设施；后续迁移推进时必须更新 schema head 检查。

## D005：离线与真实授权分层

CLI 无 online 模式；默认所有执行都是 offline；audit hook 阻止非 loopback socket 和 DNS/UDP。
即使 .env 开了 ALLOW_REAL_MODEL_CALLS，当前工厂仍无条件拒绝。后续允许真实调用必须同时满足
授权、开关、模型能力和事务预算，不能把某个 YAML 文件名当批准。

## D006：数据库专用与资源边界

独立 Compose 项目 aftercare-agent-workbench，专用命名卷，宿主端口 127.0.0.1:55432。
迁移 CLI 仅准本机 aftercare_demo/aftercare_test；没有自动清库命令。
镜像按官方仓库 metadata 锁 digest，阶段 0 未拉层/构建；现有其他项目容器和镜像不复用不修改。
模型 revision 和资源探针在阶段 2 单独提出，阶段 0 不伪填 revision。

## D007：补齐未定的模拟运费

普通退货和换货固定模拟报价 800 分，消费者承担；争议转人工。这里只显示报价，不收款。
冻结在业务规则 v1；阶段 1 服务和阶段 2 语料须一致，不能为评测题临时修改。

## D008：阶段 1—4 的执行事实

PostgreSQL 服务持有交易权限，模型只提意图；预览与明确确认分开。
checkpoint 不与业务事务绑成假分布式事务，唯一操作和永久幂等键负责重复执行。
worker 使用 PostgreSQL 队列、会话锁、租约及独立有界子进程；SSE 只读重放。
默认 UI 是脚本模拟；本机/容器均不调用真实模型。细节与真实缺陷修复见各阶段交接。

## D009：评测独立与证据分层

用户明确允许一个不继承开发上下文的独立子 Agent，仅基于冻结契约/schema/公开初态建立 100 条答案。
实现角色不读取答案，也不运行 holdout 调参；公开 manifest 只含数量、hash 和隔离声明。
60 条 dev 可用于通用修复，保留首次和最终完整报告，并对开发数据标签缺陷单独版本化。
评分器不调用生产资格函数，不要求唯一轨迹；同时检查原始终态、授权过程和实际可见告知。
6 项 mutation 保证常见篡改会失败；字面告知和有限 oracle 仍有局限，不能称完整语义评判。

## D010：配置比较与费用边界

四种工程 profile 都可离线运行。正式候选仅全文政策/完整历史基线与 full，避免昂贵地铺满四组。
阶段 5 未做真实模型比较，不声称降低 Token 或提升成功率。
compatibility-smoke 计划 6 项请求 + 2 个重试槽，最多 8 次、20k Token、并发 1；
具体请求已离线序列化、保守预留 12,600，尚未授权和发送。主模型适配器继续拒绝实际推理。


## D011：只开放获批兼容批次

阶段 6A 新建专用 smoke 入口，普通服务继续使用离线 guard；通用真实 Agent factory 仍拒绝发送。
精确计划 hash、用户审批、账户确认、临时真实开关、本地账本均校验后才可能发送。
PostgreSQL 全批会话锁与持久状态阻止并发/重复启动，HTTPTransport(retries=0)、不跟重定向、不使用代理。
每次调用先预留，之后在独立硬截止子进程中发送；响应先结算 usage，再评分协议。
未知用量保留预留并暂停；不自动消耗重试槽，不把 1M 免费余量当本批预算。
实际 6 次、1,102 Token，6/6 通过；未进行工具调用流式/严格 response_format 或完整业务 Agent 认证。
下一批 4 个开发任务的 96k/64 请求计划仅为待批封顶，不是实耗预测，也没有触发执行。


## D012：真实主 Agent 接入与首次失败保留

使用同一 BailianAdapter、单次 HTTP 传输、BudgetLedger；模型请求/响应转换为实际 LangChain 工具协议，
模型名精确固定，隐藏摘要/通用子 Agent 禁用，普通工作台不开放真实客户端。
预算/请求数按持久账本的独立会话计量，业务初态在 aftercare_test 重置，真实审计保存在 aftercare_demo。
首次四题各一次，0/4；24 请求/49,871 Token，未知预留 0。预览后改状态导致自我废弃一例；
数量不明却按整行 2 件申请三例，数量脚本用户策略有缺口。先保留原始轨迹及冻结评分，不能“修到通过”覆盖首轮。
离线增加工具依赖门禁/可信时钟，数量明确化只进入另版已见回归资产；原题、原评分和 0/4 不改。
修复后的真实回归必须独立批准新批次；两个未进入的关键阶段不得称为已验证恢复。
