# 资源清单与下载边界

日期：2026-10-17；本机 macOS ARM64。阶段 0 无需新增全局软件。

| 资源 | 实际状态 | 本轮动作 |
|---|---|---|
| Python | /opt/homebrew/bin/python3.13，3.13.14；另有 3.14 | 使用现有 3.13 建项目 .venv |
| Docker | Desktop 4.93.0，Engine/CLI 29.8.1，Compose 5.5.1 | 只读检查；服务可用 |
| Node/uv | 当前 PATH 未发现 | 不需要，不安装 |
| Python 应用/测试依赖 | 精确版本和 hash 在 requirements.lock | 仅项目隔离安装，缓存 runtime/pip-cache |
| PostgreSQL/pgvector | 本地未发现所需镜像 | 仅查 registry metadata，未拉取 |
| Python 容器基础镜像 | 本地未发现所需镜像 | 仅查 metadata，未拉取/构建 |
| embedding/reranker | 未下载、未加载 | 阶段 2 给 revision/下载量/资源探针计划 |
| 真实推理 | 未调用 | 阶段 0—5 禁止，阶段 6 单独限额授权 |

## 待授权镜像清单

精确多架构 index 和 ARM64 manifest digest 保存于 configs/images.lock.json，Compose/Dockerfile 引用 index digest。

- `python:3.13.14-slim-bookworm`：ARM64 压缩层 43,943,346 字节（约 41.9 MiB）。
- `pgvector/pgvector:pg17`：ARM64 压缩层 158,314,410 字节（约 151.0 MiB）。

合计压缩层 202,257,756 字节（约 192.9 MiB）；解压及构建后占用更大，建议为数据库/构建预留至少 2 GiB，
这不是实测峰值。构建 app 还会下载 requirements.lock 对应 Linux 发行包，估计另需数百 MB，
未构建所以没有宣称精确流量或镜像大小。不会拉取无关大型镜像。
阶段 0 没有对这些下载取得额外授权，也没有进行下载。

## 后续本地模型

计划 `BAAI/bge-small-zh-v1.5`、`BAAI/bge-reranker-base`，仅项目 runtime/models 缓存。
阶段 2 查询精确 revision 和必要文件量、列出框架依赖，再请求下载范围。
尚未完成资源探针，不虚构实际延迟、内存或向量检索分数；未批准时 BM25/接口替身可先完成。

Docker 只读检查最初受沙箱 socket 权限限制；依赖下载最初受沙箱 DNS 限制。
经授权范围内的单命令权限提升后完成检查和隔离依赖下载，没有变更全局配置。

本机安装后实测目录占用：`.venv` 约 222 MiB；`runtime`（依赖缓存与验收日志）约 64 MiB。
这是当前 macOS 运行目录，不代表 Linux 构建体积或模型加载峰值。

## 阶段 5 当前资源状态（取代上方阶段 0 的历史“未下载”状态）

用户随后已授权下载所列资源，范围内没有重复索取批准。实际已下载并构建：

- 两个固定 digest 基础镜像；app/worker 镜像实测 952,317,902 字节（约 908 MiB）。
- BAAI/bge-small-zh-v1.5 与 BAAI/bge-reranker-base，固定 revision/hash 见 configs/local-models.lock.json。
  本地权重与导出文件合计 1,320,769,921 字节；只存在项目 runtime/models。
- 本机 .venv 实测约 1.2 GiB，含 macOS 导出所需 torch/transformers；Linux lock marker 不装这些 macOS 工具。
- 本地 ONNX CPU 探针峰值 RSS 1,995,145,216 字节；两文本 embedding 首次加载+推理约 1.009s，
  reranker 两对首次加载+推理约 2.547s。小探针不代表生产负载。完整记录 docs/local-model-resource-report.json。

没有全局软件安装、模型 API 消费、公网部署或其他项目变更。
应用镜像 ID 和源文件 hash 将保存在 evaluation/manifests/release-candidate.json。
