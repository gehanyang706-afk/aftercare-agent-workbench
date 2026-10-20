# U3 首轮执行交接

唯一获批calibration-v1已执行并协议硬停止；详细报告docs/benchmarks/reports/U3-calibration-v1-first.md。
4请求，11839输入+394输出=12233Token，unknown0，约16.98秒；1个episode尝试、0个有效评分、3个未运行。
官方默认允许的混合响应被项目额外校验提前拒绝；原响应正文未保存，不能断言非空content是否仅空白或具体tool名。
先保留失败测试，再修复官方默认路由/原始响应审计/运行状态封闭。28项隔离离线契约通过，没有新真实请求。
原manifest/score/stop/trace不改，24个文件hash复核一致；READY→STOPPED的账本状态修正单独留audit，ModelCall数据完全不变。
迁移与8128离线镜像已同步健康，普通工作台真实flag仍false。历史账本160请求/322153Token/unknown0。
修复改变source fingerprint，旧批准不能再次使用；后续只有新计划、新批准与当前额度水位确认后才能调用。尚未获得完整episode成本或两配置效果，不进入优化对照/test/holdout。
