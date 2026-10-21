# U4 固定可靠性验收

240/240 次通过；12组各20次均实际触发，M=12。全部离线。

冻结源码：`bde3c0f21aba2e396f68f818030e4ae67a31f3ce`。源码指纹：`b4aed94539bd76a5b2e1ad66cb36b25dee0dba328f27e24961f9a49a4ca304d5`。
原始结果 SHA256：`ef36f08ba5441819bfc44f09e20068f8de051988b49a18e2876b5710fe1fb6f8`。累计各case耗时 626.66 秒。

|组|场景|并发|重复/通过|累计秒|
|---|---|---:|---:|---:|
|F01|duplicate_message|8|20/20|22.64|
|F02|duplicate_confirmation|2|20/20|13.72|
|F03|duplicate_confirmation|8|20/20|28.78|
|F04|last_inventory|2|20/20|13.52|
|F05|last_inventory|8|20/20|24.31|
|F06|new_intent_first|2|20/20|13.10|
|F07|commit_first|2|20/20|13.61|
|F08|lost_response_after_commit|1|20/20|4.68|
|F09|kill_parent_before_commit|2|20/20|159.68|
|F10|kill_child_after_commit|1|20/20|158.68|
|F11|lease_takeover_old_child_resumes|2|20/20|155.85|
|F12|SSE_reconnect|1|20/20|18.10|

F08全部20次均记录事务后丢响应与get_operation查询，取得原回执；F10全部20次由独立PG连接确认COMMIT后实际杀执行子进程，回执operation_id一致。
F09/F11全部记录父进程被杀后旧子进程仍存活、自然租约过期和真实新owner接管；未手写lease_owner。旧执行由已有run_guard拒绝，执行advisory lock串行化。没有为制造竞态关闭锁，也未增加未经复现需要的fencing架构。
F12实际关闭本轮独立HTTP服务器的SSE连接，随后用Last-Event-ID重复重连；无新增Agent/模型或业务调用，客户端事件去重、回执相同。

首次探索11/12及F10原始失败证据保持不变：失败输出覆盖确认绑定。修复只保留原可信输入，新增测试证明异常结果不会抹去绑定。正式240次属于修复后固定版本，不能覆写首次结果。
原始本机证据：runtime/reliability/U4-smoke-first、U4-F10-diagnose、U4-reliability-v1-first；后者results.jsonl、manifest、summary、post-audit。原始PID/消息/审批等不公开提交。

边界：F01—F07验证服务/事务；F08—F11验证离线Scripted运行时/进程；F12验证HTTP事件重放。不是LLM成功率或Agent吞吐测试。没有运行可选后端性能压测，不能填写QPS/p95 SLA。
U4后只修订公开评测专用seed/必要裁判/额度别名保护；产品与可靠性相关源码逐文件hash对比冻结提交均未变，见公开JSON与本机post-audit。公开校准使用重新冻结的源码，不能沿用旧hash。
