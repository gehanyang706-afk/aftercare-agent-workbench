# 评测隔离与命令

只在项目根目录运行。阶段 0—5 不调用真实主模型/用户模型。

```bash
.venv/bin/python -m aftercare eval validate --split dev
.venv/bin/python -m aftercare eval run --split dev --provider scripted --profile full
.venv/bin/python -m aftercare eval verify-grader
.venv/bin/python -m aftercare eval plan --batch compatibility-smoke --dry-run
```

开发集 60 题，basic/revision/boundary/recovery 各 15；公开独立 manifest 记录另 100 题，各 25。
独立角色只读冻结业务契约、schema 和初态目录，答案在 runtime/independent-evaluator/holdout.jsonl。
实现角色不读、不运行答案；阶段 5 不声称盲测成绩。答案不进 Git 或产品镜像。
同机隔离依靠角色边界与工具白名单，不声称宿主机具有密码学保密。

runner 先强制确认数据库名 aftercare_test，再重置已知表、注入时钟/初态、创建会话。
独立产品子进程接收 principal、会话、消息 ID、确认决定、故障和 profile，
不接收任务 ID、隐藏目标、未来用户策略、评分断言。场景文本永不进入产品包。
脚本用户根据实际出现的澄清/预览/完成事件选择下一句；预览与当前目标不一致便拒绝。
ModelUser 接口在离线阶段明确拒绝调用，后续启用需要单独预算授权。

每题导出原始数据库行、事件、实际可见告知和模拟用量，才重置下一题；不要与 pytest 同时运行。
这是离线脚本模式的存储隔离，真实评测不能每题清空总预算账本。
子进程每轮硬截止 180 秒，退出后回收。运行中的系统异常保留并算失败，不能移出分母。

评分器仅用原始行和独立断言：终态、可信批准绑定、禁止尝试、重复操作、必要告知均通过才算成功。
被服务层拒绝的越权提交仍计过程缺陷；正常可办理任务全转人工会失败。
不要求某条唯一工具顺序。字面告知有局限：支持 `|` 列替代措辞，但不能冒充语义模型评审。
当前 oracle 字段范围见 schema；不认识的字段直接拒绝，不能悄悄忽略。

四种配置见 configs/evaluation-profiles.yaml。完整历史基线不会截断成相同窗口；
full-policy 真正给出全部适用条款，retrieval 给 BM25 top5；full 另有结构化状态与有界读取恢复。
fixed-workflow 使用同一离线意图模型，通过固定阶段门执行，所有配置共享业务保护。
大规模正式模型对照候选为 react-full-policy/full，需先获批实测试跑再定题量。
当前脚本成功率只证明这些输入上的工程行为，不能据此声称 Agent 优于基线。

每次报告保留任务、会话和模拟请求三个分母。真实 Token/费用、独立验收成功率、
长对话泛化、重复稳定性、P95 结论均未得到阶段 5 证据。检索 Recall@5 另见既有小样本报告。
