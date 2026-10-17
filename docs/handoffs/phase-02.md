# 阶段 2：政策检索与有效诉求状态

已实现 24 份自定义模拟政策，含资格/流程、旧版/现行/未来版、时效、例外、运费、权限、缺货备选、引用与关联条款。
语料 manifest 保存内容 hash。中文分词固定为单字+相邻双字+英文数字单元，非空格分词。
BM25、dense、RRF(k=60) 和 rerank 可切换；向量持久化为 PostgreSQL vector(512)，以 cosine 精确排序。

## 运行、实际验证与证据

在项目根目录：

```bash
.venv/bin/python -m aftercare db migrate
.venv/bin/python -m aftercare retrieval build --profile local-lite
.venv/bin/python -m aftercare retrieval inspect --query "收到十天了能换大一码吗" --profile hybrid-rerank
.venv/bin/python -m aftercare retrieval evaluate --split dev --profiles bm25,dense,hybrid,hybrid-rerank
AFTERCARE_TEST_DATABASE_URL=postgresql+psycopg://aftercare:aftercare_local_only@127.0.0.1:55432/aftercare_test .venv/bin/python -m pytest tests/retrieval tests/unit/test_case_state.py
```

上述迁移/构建/评测退出码均 0；构建 24 chunks、512 维。相关测试 **7 passed，0 skipped**，退出码 0。
`runtime/phase-02/{build.json,tests.log,junit.xml,retrieval-report.json,probe.log}` 为原始证据。
可跟踪报告：docs/experiments/retrieval-dev.json、docs/local-model-resource-report.json。
静态/格式检查和 pip check 通过。真实 API 模型调用 0。

预先定义的 12 条公开检索开发问题上 Recall@5：BM25 **11/12**；dense、hybrid、hybrid-rerank 各 **12/12**。
这是小型已见开发集，不是业务任务成功率，也不证明检索在大语料/陌生任务上优于完整政策基线。
完整政策基线保留全部适用条款，不人为截断制造优势。

## 资源与取舍

用户授权下载后，仅在 runtime/models 保存以下固定 revision 的必要文件：

- BAAI/bge-small-zh-v1.5：7999e1d3359715c523056ef9478215996d62a620。
- BAAI/bge-reranker-base：2cfc18c9415c912f9d8155881c133215df768a70。

为避免 Linux CUDA/NVIDIA 依赖，运行统一用 ONNX CPU，2 个线程。embedding 在 macOS 用官方 safetensors
本地导出，源 revision、导出 hash、框架版本和数值对照见 configs/embedding-export.json；reranker 用官方 ONNX。
模型文件实际共 1,320,769,921 字节（包括导出文件和源 safetensors），下载不重复收集多套权重格式。
实测首次加载并编码 2 条文本约 1.01 秒，首次加载并重排 2 对约 2.55 秒，进程峰值 RSS 约 1.86 GiB。
这是本机单进程探针，不是并发容量或冷盘性能保证。尚无真实远程对话模型调用。
依赖仍只有一个 requirements.lock；PyTorch/transformers 仅 macOS 导出需要，Linux 运行 ONNX。

## 数据流与完整机制

订单资格版本/现行流程版本 → 元数据预过滤 → 中文 BM25 top20 + 精确 dense top20 → RRF →
去重后的 top10 重排 → 完整条款 top5 + source/version/section/hash。
缓存键含模型 revision、语料 hash、政策版本、候选有效集合、query/profile，最多 256 项。
条款不在 tokenizer 中截断；超过限制明确失败。找不到适用条款不构造成功答案。

有效状态机制：用户消息先持久化并增加 revision/失效预览 → update_case 核验来源是本会话当前用户消息和 CAS revision →
显式更新当前订单/商品/意图/constraints，旧值进入 superseded → 上下文装配当前事实+近期完整消息+相关证据。
“大一码”改成“黑色原码”使用完整新约束替换旧约束；换订单清除旧商品行。历史消息仍完整可回放。

五个入口：retrieval/engine.py；retrieval/local.py；services/case_state.py；
retrieval/evaluate.py；scripts/export_embedding.py。

## 实际故障与修复

导出后新增的严格数值对照曾失败（最大误差 0.93）；检查 PyTorch 导出上下文源码发现包装层默认 training=True，
恢复时递归启用了原模型 Dropout。修复为整个 Encoder 显式 eval 后再导出/对照，保留 1e-4 阈值，不改阈值掩盖差异。
并在创建 ONNX session 前关闭其原生遥测。最终误差见 configs/embedding-export.json。

## 状态与限制

已实现/已验证：24 政策、版本过滤、BM25/dense/hybrid/rerank、pgvector、真实本地推理、引用/条款完整性、有效状态与来源追踪。
待真实模型验证：Agent 是否正确选择证据、理解改口；不能用替身结果证明语义能力。
未实现：主 Agent/HITL/预算、Web/worker/SSE、独立业务评测。
实际工程取舍为单主 Agent 的小语料精确检索，未加 ANN 索引/多服务。没有调整开发问题或评分来追求提升。

体验任务：对“收到十天能换大一码吗”比较 BM25 与 hybrid-rerank 的引用，再读改口状态测试。
三个问题：为什么先过滤版本再比相似度？检索证据为何不能当实时库存？旧消息为何保留但旧约束要失效？
下一阶段：检查已安装 Deep Agents 的默认工具，接单主 Agent、可信确认中断恢复、预算网关和假模型契约；远程调用仍禁止。
