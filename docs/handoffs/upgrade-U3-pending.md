# U3待批交接（未执行）

固定2项train任务107/96，每题official_tc与harness_full_history一次，共4episode。
执行源码提交：`b4004bc27b32dc0918c6acdcf1742871db63fac8`。
源码指纹：`d3b6741129c150e1676a3052b44111c516d01c172fae9c90a72bc7277bdff92a`。
计划hash：`d88ea97b575e766aed30e86a036d1499a4f8285ceac16575a2b67289e5d6c539`。
具体角色、输出/请求/Token/时间上限、样本预留、停止规则：evaluation/manifests/benchmark-v1/calibration-v1.json。
易读预算说明：docs/benchmarks/reports/U3-calibration-budget.md。
Agent/用户/必要裁判统一qwen3.5-plus-2026-02-15，北京，关闭思考；最多162 HTTP、1.4M输入输出Token、2400秒、并发1、费用0。
裁判仅107的两个episode，保留官方NL奖励；共同配置替换默认GPT-4.1裁判模型，不能冒充排行榜原配置。
没有真实调用，没有批准文件或本轮当前账户确认。预检已验证缺授权拒绝。

待执行前条件：明确批准该hash与全部角色；当前精确模型免费余量≥1.4M、FreeTierOnly、北京地域；增量0006账本迁移及应用版本协调完成。
现demo与8128是旧0005候选，未改变；不得直接迁移后留旧镜像假称健康，不清库/不重置Budget(project)。
由后续获批执行在发送前完成离线迁移/镜像协调和新旧账本逐行核对；源码与计划若需改变必须重新冻结，不沿用本批准。
普通任务失败继续固定剩余；硬预算/安全/协议/认证/unknown停止全部，不重跑不自动续跑。
旧六题、test/holdout、正式对照均不执行；后续4+4开发预算只能依据校准结果另行提交。
