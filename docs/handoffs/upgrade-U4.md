# U4：固定可靠性试验

12组×20次清单在 evaluation/manifests/benchmark-v1/reliability-v1.json；仅aftercare_test。
首次探测及F10失败证据保留 runtime/reliability/U4-smoke-first、U4-F10-diagnose。
根因：worker异常输出覆盖可信确认输入；修复为结果中保留原绑定，不伪造确认。针对性测试与真实进程恢复已通过。
正式运行前冻结实现；Barrier/IPC控制事务前、真实COMMIT后、claim与job完成点；不以sleep安排竞态，不手改lease_owner。
F10独立连接确认operation已落库后杀实际子进程，并在父进程finalize前杀父进程；新worker自然租约接管，恢复原回执。
F09/F11记录父死后存活子进程，旧子进程恢复时由原事务run_guard拦截；执行advisory lock会串行化，未制造不可能的并发。
F12本轮自建loopback HTTP服务、实际关闭SSE连接后重复游标重连，校验无新调用/副作用。
进程PID与启动时间来自本轮创建进程，清理仅触及这些PID；不动用户容器。
最终结果：240/240通过，12组各20次实际触发且断言达标，M=12。
累计case耗时626.66秒；原始results SHA256 ef36f08ba5441819bfc44f09e20068f8de051988b49a18e2876b5710fe1fb6f8。
F08事务后故障与get_operation查询、F10独立PG已提交验证和同op回执、F09/F11存活旧子进程及新owner、F12真实SSE断连重连均额外复核20/20。
公开报告docs/benchmarks/reports/U4-reliability-v1.md及JSON；完整PID/审批/状态证据留本机runtime。
全量离线253 passed/3 skipped；两项官方依赖在隔离环境验收，PG健康检查显式test URL补验1 passed。
U4后官方校准专用seed/裁判/别名保护另行修订，隔离契约23 passed；产品与可靠性组件逐文件核对U4冻结提交未变，不额外重跑240次。
关键机制：COMMIT是业务事实，checkpoint/job输出是另一个持久边界；进程可在两者之间死亡，恢复必须用原批准事件查询同一operation，而不是重建一笔业务。
限制：不是模型效果或吞吐测量；没有运行可选后端压测、U3、test/holdout。
