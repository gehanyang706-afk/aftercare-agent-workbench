"""Author simulated merchant policies; no evaluation tasks or hidden answers."""

import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
# (source, title, action, kind, section text). Old/future documents are genuine version controls.
POLICIES = [
    (
        "cancel",
        "取消订单资格",
        "cancel",
        "qualification",
        (
            "仅 PAID_UNSHIPPED 已支付未发货订单可以整单取"
            "消；有活动售后时不得取消。SHIPPED 和 DELIVER"
            "ED 均不符合取消条件。"
        ),
    ),
    (
        "refund",
        "取消后的模拟退款",
        "cancel",
        "process",
        "取消成功仅创建原支付整数分金额的模拟退款请求。不得告知退款已到账，也不接入支付渠道。",
    ),
    (
        "return-window",
        "退货时效",
        "return",
        "qualification",
        (
            "订单 DELIVERED 后 7×24 小时（168 小时）"
            "内可申请退货，含恰好 168 小时；超过 1 微秒也不符合普"
            "通时效。未交付不能办理。"
        ),
    ),
    (
        "exchange-window",
        "换货时效",
        "exchange",
        "qualification",
        (
            "订单 DELIVERED 后 15×24 小时（360 小时"
            "）内可以申请换货，含边界；收到十天可按换货规则复核，退货七天"
            "时效不能套用换货。"
        ),
    ),
    (
        "unused-return",
        "退货商品状态",
        "return",
        "qualification",
        (
            "普通可退商品必须未使用；已使用、定制印字商品不可走普通退货。"
            "质量争议不得擅自判断，应转人工。"
        ),
    ),
    (
        "unused-exchange",
        "换货商品状态",
        "exchange",
        "qualification",
        "商品需未使用且可换。定制品及不可换分类不支持普通换货；质量争议需要人工处理。",
    ),
    (
        "same-family",
        "换货变体限制",
        "exchange",
        "qualification",
        (
            "仅同一商品系列、相同整数分价格的不同变体可以换货。不能将短袖"
            "换运动鞋，不得收补差价后跨价办理。"
        ),
    ),
    (
        "size",
        "尺码更换",
        "exchange",
        "process",
        (
            "大一码、小一码和颜色变化都需查询实时变体。用户从大一码改成白"
            "色原码时，删除旧尺码约束并记录新消息来源；目标仍相同则需澄清"
            "。"
        ),
    ),
    (
        "inventory",
        "库存预留规则",
        "exchange",
        "process",
        (
            "预览库存只是快照，不占用库存等待用户。提交事务重新查库存；不"
            "足则 STATE_CHANGED 并重做方案，不能超卖。"
        ),
    ),
    (
        "release",
        "库存预留释放",
        "exchange",
        "process",
        (
            "有效换货申请持续预留库存。显式拒绝或撤回才释放；换货完成消耗"
            "预留，不重新增加可售库存。没有静默超时释放。"
        ),
    ),
    (
        "return-fee",
        "普通退货运费",
        "return",
        "process",
        (
            "消费者承担普通退货模拟运费报价 800 分（8 元）。V1 "
            "仅展示、不实际收款或从退款扣减；运费责任争议转人工。"
        ),
    ),
    (
        "exchange-fee",
        "普通换货运费",
        "exchange",
        "process",
        "消费者承担普通换货模拟运费报价 800 分（8 元）。V1 不实际收取，不声称已寄出；争议转人工。",
    ),
    (
        "quantity-return",
        "退货数量",
        "return",
        "qualification",
        (
            "一次申请一个订单中的一个商品行和数量。活动退换占用数量总和不"
            "得超过购买数量；需先拒绝或撤回才可释放相应申请额度。"
        ),
    ),
    (
        "quantity-exchange",
        "换货数量",
        "exchange",
        "qualification",
        (
            "一个商品行的活动换货和退货合计不可超过原购买数量，不得同时把"
            "同一件商品退又换。数据库事务复核占用数量。"
        ),
    ),
    (
        "fallback",
        "缺货备选路径",
        "exchange",
        "process",
        (
            "换货缺货时不得自动改成退货。只有用户明确授权可退货备选，才能"
            "提出新的退货预览；仍需满足退货七天时效、并再次确认。"
        ),
    ),
    (
        "approval",
        "可信操作确认",
        "all",
        "process",
        (
            "每次写操作先展示参数、对象、政策和模拟费用，再用结构化确认按"
            "钮。聊天“好的”不视为批准；用户改口立刻使旧预览失效。"
        ),
    ),
    (
        "receipt",
        "申请成功的告知",
        "all",
        "process",
        (
            "只有 COMMITTED operation 回执能证明提交。退换成功仅代表 RETURN"
            "_REQUESTED 或 EXCHANGE_REQUESTED；未完成退款/寄货。提交响应"
            "丢失先查原回执。"
        ),
    ),
    (
        "identity",
        "用户订单权限",
        "all",
        "process",
        (
            "只查询服务端身份所属订单；模型不能指定 principal、"
            "批准状态或写库金额。越权与不存在返回统一 NOT_FOUND"
            "，不泄露别人的订单内容。"
        ),
    ),
    (
        "dispute",
        "质量与超范围人工处理",
        "all",
        "process",
        (
            "疑似质量争议、超范围要求和无法确定政策时建立 HANDOFF"
            "_PENDING 人工工单，附必要证据摘要；不认定责任、不对"
            "外发消息。"
        ),
    ),
    (
        "version",
        "政策版本选择",
        "all",
        "process",
        (
            "购买时承诺的资格政策随订单固定，流程政策取申请时有效版本。任"
            "何被预览依赖的政策改变都要重新校验并生成新的确认。"
        ),
    ),
]


def main():
    directory = ROOT / "data/policies"
    directory.mkdir(parents=True, exist_ok=True)
    docs = []
    for key, title, action, kind, content in POLICIES:
        docs.append(
            dict(
                source_id=key,
                title=title,
                version="v1",
                action=action,
                kind=kind,
                category="all",
                effective_from="2026-01-01T00:00:00Z",
                effective_to=None,
                sections=[{"section": "rule", "text": content, "related": []}],
            )
        )
    for action, hours in [("return", 336), ("exchange", 720)]:
        docs.append(
            dict(
                source_id=action + "-window",
                title="旧版" + action + "时效",
                version="v0",
                action=action,
                kind="qualification",
                category="all",
                effective_from="2025-01-01T00:00:00Z",
                effective_to="2026-01-01T00:00:00Z",
                sections=[
                    {
                        "section": "rule",
                        "text": (
                            f"此为旧版购买资格：交付后 {hours} 小时内，"
                            "未使用且可退换商品可申请。"
                            "不得用于 v1 购买承诺订单。"
                        ),
                        "related": [],
                    }
                ],
            )
        )
    for action in ["return", "exchange"]:
        docs.append(
            dict(
                source_id=action + "-fee",
                title="未来版运费流程",
                version="v2",
                action=action,
                kind="process",
                category="all",
                effective_from="2027-01-01T00:00:00Z",
                effective_to=None,
                sections=[
                    {
                        "section": "rule",
                        "text": "未来运费条款，不适用于 2026 年流程；未到生效时间禁止使用。",
                        "related": [],
                    }
                ],
            )
        )
    related = {
        "fallback": ["return-window@v1#rule"],
        "inventory": ["release@v1#rule"],
        "unused-return": ["dispute@v1#rule"],
        "unused-exchange": ["dispute@v1#rule"],
    }
    for doc in docs:
        doc["sections"][0]["related"] = related.get(doc["source_id"], [])
    manifest = []
    for doc in docs:
        path = directory / f"{doc['source_id']}.{doc['version']}.yaml"
        raw = yaml.safe_dump(doc, allow_unicode=True, sort_keys=False)
        path.write_text(raw)
        manifest.append(
            {
                "file": str(path.relative_to(ROOT)),
                "sha256": hashlib.sha256(raw.encode()).hexdigest(),
            }
        )
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"documents": len(docs)}))


if __name__ == "__main__":
    main()
