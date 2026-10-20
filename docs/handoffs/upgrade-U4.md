# U4：固定可靠性试验

12组×20次清单在 evaluation/manifests/benchmark-v1/reliability-v1.json；仅aftercare_test。
首次探测及F10失败证据保留 runtime/reliability/U4-smoke-first、U4-F10-diagnose。
根因：worker异常输出覆盖可信确认输入；修复为结果中保留原绑定，不伪造确认。针对性测试与真实进程恢复已通过。
正式运行前冻结实现；Barrier/IPC控制事务前、真实COMMIT后、claim与job完成点；不以sleep安排竞态，不手改lease_owner。
F10独立连接确认operation已落库后杀实际子进程，并在父进程finalize前杀父进程；新worker自然租约接管，恢复原回执。
F09/F11记录父死后存活子进程，旧子进程恢复时由原事务run_guard拦截；执行advisory lock会串行化，未制造不可能的并发。
F12本轮自建loopback HTTP服务、实际关闭SSE连接后重复游标重连，校验无新调用/副作用。
进程PID与启动时间来自本轮创建进程，清理仅触及这些PID；不动用户容器。
最终结果将在运行完成后追加；当前不预填M。
