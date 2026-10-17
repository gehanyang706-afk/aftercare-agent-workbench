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
