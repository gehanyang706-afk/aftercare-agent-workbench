# 独立验收角色任务（实现角色不读取答案）

只读取 docs/business-contract.md、evaluation/schema/scenario.py、data/demo/catalog.json。
不读取产品实现、开发场景、开发评分或开发 Trace，不修改产品、工具或评分器。
在 runtime/independent-evaluator/holdout.jsonl 编写 100 条场景，四类 basic/revision/boundary/recovery 各 25。
采用独立的 family_id（h-前缀），不以近似措辞改写凑数量。组合时间、数量、权限、商品类型、意图变化和恢复边界。
所有条目符合 Scenario schema，明确初态/目标/可允许及禁止变化/必要告知。字段说明以 schema/catalog 为准。
principal 可在 user_known_facts 中明确指定，默认 alice；实际给产品的只有逐轮 user_message，不能暴露场景 ID、隐藏目标/答案/未来脚本/故障安排。
可用脚本仅包含语法或 schema 检查；不要运行或调试产品，不因产品表现修改答案。

同时输出 evaluation/manifests/holdout-manifest.json：只包含场景数、分类/家族数、文件 sha256、作者隔离声明、未进行真实模型运行声明，不包含任何答案/用户未来脚本。
完成后仅向父角色报告公开 manifest 路径、总数/分类计数、schema 是否通过；不要发答案或案例详情。
不要生成外部消息或调用真实模型/API；不下载资源。不得修改本任务授权外的其他文件。

评分断言字段只使用 schema.py 末尾列出的键；不能用未定义字段制造无法评分的答案。
为避免模板族泄漏，开发集限定以下简单单因素族：基础单次取消/退货/尺码更换/查询/澄清；
单次意图或目标变更；单一权限/时效/使用状态边界；单一故障/重复请求。
独立集请使用组合条件、不同先后顺序、两次及以上纠正、澄清后再变更、异商品/数量/库存条件组合等独立模板族，
不得仅改写基础句子的措辞。保留场景失败也不为产品调参。
