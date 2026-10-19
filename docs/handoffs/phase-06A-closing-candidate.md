# 收尾候选交接

2026-10-19。进入收尾，停止新增功能和提示词迭代。本轮0真实模型请求；最后固定开发验收尚待批准，不宣称最终真实验收完成。

## 已交付与验证

源码7fba4b7150f5d85441c9e69a4b863d9620130840；指纹162ba7313e5451960d80a5544b4a77c769c72a1dcb737165c22860af257d0f06。
来源核对：case.source_message_id只是模型提议锚点，新增provenance=model_proposal并在真实模型上下文展示，另列实际user数量证据；不改提议值或抹去错误。中文紧邻订单号识别修复，跨订单数量清空。明确暂停沿用共享runtime。含真实批次账本的demo reset安全拒绝。
全量237 passed/0 skipped/55.98秒；有修复前失败证据。六题default/preview-stop各5/6，fa1-03替身不识别“大一号”，被INVALID_EXCHANGE_VARIANT拒绝，保留原题和失败，不加脚本特判。暂停两题实际走PAUSED_BY_USER/NOT_INVOKED、无副作用。ruff与diff检查通过。
8128 app/worker均更新候选镜像134719c52533fefeedbba3469f4cd037c43eb16ad74ad8d19fedb42450c5d8a5；关键源码/requirements.lock与宿主核对一致，ALLOW_REAL_MODEL_CALLS=false。实际API→worker暂停烟测通过，0模型/0提交。旧镜像420381…保存before-final-acceptance标签。没有下载镜像、改全局环境或清数据库。
真实历史仍156请求/309,920已知Token，新批次0请求。上批95份原始文件哈希未变，用户原有报告编辑未动；不回写成绩。

## 唯一待批计划

final-development-acceptance-v1；hash a5eecada94b4088659873a28a6e0dcc46afb99256006eec868da5ddf46a9e21d。
六题：明确1件换货、退1件保留另一件、相对尺码、预览后改口、明确2件缺货暂停、缺量澄清2件后缺货暂停。固定顺序各一次，script-user-v3显式选择；冻结grader和process-diagnostic-v5不改，人工复核补足字段边界。
qwen3.5-plus-2026-02-15，北京，关闭思考，full，并发1。每题16请求/300秒；Token 40k/40k/40k/48k/40k/56k；总96请求/264k/1800秒，额外付费0。预计43–69请求/99k–169k/210–460秒，估计不是保证。
执行前仍需具体批准与当前免费余量至少264k、北京及FreeTierOnly确认。旧批准/余额不继承；专用源码入口，不用镜像执行真实评测。只清aftercare_test，账本aftercare_demo保留，无并发pytest。普通失败继续，安全/认证/额度/协议/unknown usage/硬上限停止后续请求。
计划本身不是批准，本轮未创建批准或账户确认；无新的模型用户/裁判、holdout或架构对照。

## 收尾方式与完整机制

验收后记录首次结果并冻结最终版；仅错误提交、授权绕过、重复副作用、虚假回执告知或预算安全异常阻断。其他模型/脚本/文案/未覆盖问题写已知限制，不自动新增真实回归。任何阻断修复后的真实调用仍需另批。候选资料已完成，验收后只补真实结果和最终身份，不再开功能迭代。
完整机制：用户原始消息→可信数量证据（无量为null）与模型case提议分别装配→工具提议留痕→后台预览校验→可信批准绑定→HITL恢复或图结束续跑→同一幂等事务→回执告知；明确暂停作为独立应用事件，零模型执行。来源、动作权限、图状态、业务终态和冻结评分不能混为一个“成功”。
关键入口：agent/context.py、services/case_state.py、services/intent_guard.py、agent/runtime.py、llm/regression_scope.py。政策/库存/事务服务未放宽。

## 当前运行与资料

启动/停止/无网络重建/回滚见docs/operations.md；五分钟演示见docs/closing/demo-script.md；历史分母和限制见results-summary.md；事实来源见fact-sources.md；面试见interview-handoff.md；精确预算见final-acceptance.md。
可用工作台http://127.0.0.1:8128，默认离线。演示使用新会话，别清账本；仅在愿意消耗模拟数据时点击确认。当前健康标签为历史基础设施标签，镜像/源码身份以freeze为准。
已验证为工程安全机制与特定已见真实轨迹，不代表泛化、生产支付物流、所有数量行为稳定或架构优于基线。复杂语言/冗余追问/被拦猜量/替身表达覆盖均保留限制。
自检：消息锚点为什么不是证据？为什么5/6脚本预演不等于真实模型5/6？为什么最后验收后普通失败不触发再调一轮？答案分别见来源元数据、替身边界与收尾闸门。
