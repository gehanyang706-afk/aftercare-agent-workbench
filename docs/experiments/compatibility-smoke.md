# compatibility-smoke 实际结果

2026-10-17，北京地域配置，精确请求与返回模型均为 `qwen3.5-plus-2026-02-15`，关闭思考。
获批计划 hash：`3392fe79d3877477b2d8acc2cfebbd58a46c6486b0b77279c632af967e8357f1`。

| 检查 | 实际结果 | 输入 Token | 输出 Token | 单项耗时（秒） |
|---|---|---:|---:|---:|
| 普通文字 | HTTP 200，返回 OK | 16 | 1 | 1.628 |
| 工具调用 | get_order，参数仅 order_id=S1002 | 291 | 30 | 3.383 |
| 工具结果回传 | 消费冻结的 ToolMessage，回答 S1002 状态 | 354 | 10 | 2.099 |
| 流式 usage | OK、[DONE] 与末块 usage 均收到 | 18 | 1 | 1.554 |
| 可校验 JSON | action=query、order_id=S1002，校验通过 | 29 | 29 | 2.447 |
| 工具参数 schema | 第二次合法工具名/参数，无额外身份字段 | 293 | 30 | 2.754 |
| 合计 | **6/6 通过，6 次请求，0 重试** | **1,001** | **101** | **批次 13.933** |

实际总量 1,102 Token；上限 20,000。最多 8 次的两个重试槽未使用，未发送额外请求。
PostgreSQL 核对 6 条 SETTLED，账本总量 1,102，未知调用 0，剩余预留 0；批次无暂停。
完整逐项 request_id、模型、finish_reason、账本核对见同名 JSON；原始响应在 runtime/phase-06A。
账单和控制台余量未独立查询；免费余额与用完即停依据用户明确确认，额外付费授权为 0。

## 问题、修复与实际边界

配置预检发现 Base URL 使用原生 `/api/v1`，在发送前改为同地域 `/compatible-mode/v1`。
这是本地路径修正，不换地域、模型或批次；预检期间请求 0。
真实请求均成功，无需线上代码修复或重试。发送前离线回归 66 passed，0 skipped。

工具回传使用已冻结的独立消息 fixture，不是把第二次请求生成的 call_id 动态串接到第三次。
JSON 是实际可校验输出，不是 response_format 严格模式认证；两个合法工具输出也不证明服务端强制约束解码。
只测文字流及末块 usage，未测流式工具调用；未验证完整九工具售后 Agent、语言泛化、吞吐或真实业务成功率。
工作台仍是离线脚本模式。下一批开发试跑未获批，独立验收集未读、未运行。

## 下一批待批计划

`evaluation/manifests/development-pilot.json`：同一精确模型与 full 配置，脚本用户，4 个开发任务各 1 次：
取消、尺码换货、确认前换货改退货、提交响应丢失查询原回执。
每会话最多 16 次请求/24k Token；合计最多 64 次/96k Token，含所有重试。
输出最多 512 Token/请求，并发 1，单会话 180 秒、批次 20 分钟，额外付费预算 0。
必须先补齐完整真实 Agent 适配与预算/fixture 隔离回归；不能把离线评测的清库方式套在真实调用账本上。
96k 是封顶，不是基于本次短提示估算的实际消耗；预算截止与所有失败保留在任务分母中。
此计划状态 DRAFT_NOT_AUTHORIZED，不会自动执行或进入正式对照。

官方接口依据：[地域](https://help.aliyun.com/zh/model-studio/regions)、
[思考参数](https://help.aliyun.com/zh/model-studio/deep-thinking)、
[流式 usage](https://help.aliyun.com/en/model-studio/stream)、
[免费额度保护](https://help.aliyun.com/zh/model-studio/new-free-quota)。
这些说明不替代本账户保护状态的用户确认或真实响应证据。
