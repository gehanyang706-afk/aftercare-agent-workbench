"""Auditable development fixtures; never imported by product code."""

from pathlib import Path

from evaluation.schema.scenario import Scenario

CASES = []


def add(
    category,
    family,
    text,
    goal,
    *,
    changes=(),
    steps=(),
    faults=(),
    expected=None,
    communications=None,
    principal="alice",
):
    action = goal.get("action")
    writes = goal.get("accept", True) and action in {"cancel", "return", "exchange"}
    invariants = {
        "operation_count": int(writes),
        "application_count": int(writes and action != "cancel"),
        "refund_count": int(writes and action == "cancel"),
        "handoff_count": 0,
    }
    if writes:
        invariants.update(
            {
                k: v
                for k, v in goal.items()
                if k in {"order_id", "action", "target_variant", "quantity"}
            }
        )
        invariants["result"] = "CANCELLED" if action == "cancel" else action.upper() + "_REQUESTED"
    if expected:
        invariants.update(expected)
    notice = (
        ["模拟退款请求"]
        if writes and action == "cancel"
        else ["尚未退款或寄出换货", "800"]
        if writes
        else []
    )
    case = Scenario(
        scenario_id=f"d-{len(CASES) + 1:03}",
        family_id="d-" + family,
        category=category,
        split="dev",
        seed=len(CASES) + 1,
        clock="2026-10-17T04:00:00Z",
        fixture_changes=list(changes),
        initial_user_message=text,
        hidden_user_goal=goal,
        user_known_facts={"principal": principal},
        user_behavior_policy=list(steps),
        fault_schedule=list(faults),
        expected_state_invariants=invariants,
        required_communications=notice if communications is None else communications,
    )
    CASES.append(case)


def order(oid, **fields):
    return {"table": "orders", "id": oid, "fields": fields}


def line(oid, **fields):
    return {"table": "order_lines", "id": oid + "-1", "fields": fields}


def goal(action, oid="S1002", **kw):
    return {"action": action, "order_id": oid, **kw}


def say(on, text):
    return {"on": on, "say": text}


def fault(kind, **kw):
    return {"kind": kind, "trigger": "after_preview", **kw}


def build():
    add(
        "basic",
        "paid-cancellation",
        "取消订单 S1001",
        goal("cancel", "S1001"),
        expected={"order_status": "CANCELLED"},
    )
    add("basic", "ordinary-return", "S1002 退货", goal("return", quantity=1))
    add("basic", "relative-size", "S1002 换大一码", goal("exchange", target_variant="tee-white-L"))
    add("basic", "color-change", "S1002 换黑色原码", goal("exchange", target_variant="tee-black-M"))
    add(
        "basic",
        "numeric-shoe-size",
        "S1003 换 41 码",
        goal("exchange", "S1003", target_variant="shoe-black-41"),
    )
    add("basic", "explicit-size", "S1002 换白色 L", goal("exchange", target_variant="tee-white-L"))
    add(
        "basic",
        "query-only",
        "查询 S1004 的状态",
        goal("query", "S1004"),
        communications=["SHIPPED"],
    )
    add("basic", "missing-order", "我要退货", goal("return"), steps=[say("clarification", "S1002")])
    add(
        "basic",
        "missing-intent",
        "看看 S1001",
        goal("cancel", "S1001"),
        steps=[say("clarification", "取消订单")],
    )
    add(
        "basic",
        "missing-target",
        "S1002 换货",
        goal("exchange", target_variant="tee-black-M"),
        steps=[say("clarification", "黑色原码")],
    )
    add(
        "basic",
        "manual-quality",
        "S1002 质量有问题请人工",
        goal("handoff"),
        expected={"handoff_count": 1},
        communications=["人工"],
    )
    add(
        "basic",
        "decline-preview",
        "S1002 退货",
        goal("return", accept=False),
        steps=[{"on": "preview", "decision": "reject"}],
    )
    add("basic", "two-unit-return", "S1002 退货数量 2 件", goal("return", quantity=2))
    add("basic", "bob-owned-order", "S2001 退货", goal("return", "S2001"), principal="bob")
    add(
        "basic",
        "all-orders-clarification",
        "帮我处理售后",
        goal("query"),
        communications=["订单编号"],
    )

    for family, initial, correction, final in [
        ("exchange-to-return", "S1002 换大一码", "改为退货", goal("return")),
        (
            "return-to-exchange",
            "S1002 退货",
            "改为换黑色原码",
            goal("exchange", target_variant="tee-black-M"),
        ),
        (
            "size-to-color",
            "S1002 换大一码",
            "改为换黑色原码",
            goal("exchange", target_variant="tee-black-M"),
        ),
        (
            "color-to-size",
            "S1002 换黑色原码",
            "改为换白色 L",
            goal("exchange", target_variant="tee-white-L"),
        ),
        ("explicit-order-switch", "S1002 退货", "改为 S1001 取消订单", goal("cancel", "S1001")),
        ("cancel-to-return-order", "S1001 取消订单", "改为 S1002 退货", goal("return")),
        (
            "shirt-to-shoe",
            "S1002 换大一码",
            "改为 S1003 换大一码",
            goal("exchange", "S1003", target_variant="shoe-black-41"),
        ),
        ("manual-instead", "S1002 退货", "改为人工处理质量争议", goal("handoff")),
        ("used-disclosure", "S1002 退货", "这件已经穿过了", goal("handoff")),
        ("quantity-change", "S1002 退货", "退货改为数量 2 件", goal("return", quantity=2)),
        ("abandon-intent", "S1002 换大一码", "不换了", goal("query", accept=False)),
        ("query-to-action", "查询 S1002 状态", "我要退货", goal("return")),
        ("clarify-order-before-action", "退货", "S1002", goal("return")),
        (
            "clarify-shoe-target",
            "S1003 换货",
            "41 码",
            goal("exchange", "S1003", target_variant="shoe-black-41"),
        ),
        ("reject-with-correction", "S1002 换黑色原码", "先不换，改为退货", goal("return")),
    ]:
        trigger = (
            "clarification"
            if family in {"query-to-action", "clarify-order-before-action", "clarify-shoe-target"}
            else "preview"
        )
        add(
            "revision",
            family,
            initial,
            final,
            steps=[say(trigger, correction)],
            expected={"handoff_count": 1} if final["action"] == "handoff" else None,
        )

    for family, text, changes, expected, communication in [
        ("return-at-168h", "S1002 退货", [order("S1002", delivered_age_hours=168)], None, None),
        (
            "return-over-168h",
            "S1002 退货",
            [order("S1002", delivered_age_hours=168.001)],
            {"handoff_count": 1},
            ["人工"],
        ),
        (
            "exchange-at-360h",
            "S1003 换大一码",
            [order("S1003", delivered_age_hours=360)],
            None,
            None,
        ),
        (
            "exchange-over-360h",
            "S1003 换大一码",
            [order("S1003", delivered_age_hours=360.001)],
            {"handoff_count": 1},
            ["人工"],
        ),
        ("shipped-cancel", "取消订单 S1004", [], {}, ["INELIGIBLE_STATUS"]),
        ("foreign-principal", "S2001 退货", [], {}, ["NOT_FOUND"]),
        ("used-line", "S1002 退货", [line("S1002", unused=False)], {"handoff_count": 1}, ["人工"]),
        (
            "quantity-occupied",
            "S1002 退货",
            [line("S1002", occupied=2)],
            {},
            ["QUANTITY_UNAVAILABLE"],
        ),
        ("zero-stock", "S1002 换 XL", [], {"handoff_count": 1}, ["人工"]),
        (
            "nonreturnable",
            "S1002 退货",
            [{"table": "variants", "id": "tee-white-M", "fields": {"returnable": False}}],
            {"handoff_count": 1},
            ["人工"],
        ),
        (
            "nonexchangeable",
            "S1002 换大一码",
            [{"table": "variants", "id": "tee-white-M", "fields": {"exchangeable": False}}],
            {"handoff_count": 1},
            ["人工"],
        ),
        (
            "unequal-price",
            "S1002 换大一码",
            [{"table": "variants", "id": "tee-white-L", "fields": {"price_fen": 10000}}],
            {},
            ["INVALID_EXCHANGE_VARIANT"],
        ),
        ("same-variant", "S1002 换白色 M", [], {}, ["INVALID_EXCHANGE_VARIANT"]),
        ("missing-size", "S1002 换小一码", [], {}, ["没有匹配"]),
        ("return-of-unshipped", "S1001 退货", [], {}, ["INELIGIBLE_STATUS"]),
    ]:
        success = family in {"return-at-168h", "exchange-at-360h"}
        act = "exchange" if "换" in text else "cancel" if "取消" in text else "return"
        g = goal(
            act,
            "S1003"
            if "S1003" in text
            else "S1004"
            if "S1004" in text
            else "S2001"
            if "S2001" in text
            else "S1001"
            if "S1001" in text
            else "S1002",
            accept=success,
        )
        if success and act == "exchange":
            g["target_variant"] = "shoe-black-41"
        add(
            "boundary",
            family,
            text,
            g,
            changes=changes,
            expected=expected,
            communications=communication,
        )

    for family, text, g, f, exp in [
        (
            "cancel-response-lost",
            "取消订单 S1001",
            goal("cancel", "S1001"),
            fault("lost_response"),
            None,
        ),
        ("return-response-lost", "S1002 退货", goal("return"), fault("lost_response"), None),
        (
            "exchange-response-lost",
            "S1002 换大一码",
            goal("exchange", target_variant="tee-white-L"),
            fault("lost_response"),
            None,
        ),
        (
            "cancel-checkpoint-restart",
            "取消订单 S1001",
            goal("cancel", "S1001"),
            fault("restart"),
            None,
        ),
        ("return-checkpoint-restart", "S1002 退货", goal("return"), fault("restart"), None),
        (
            "exchange-checkpoint-restart",
            "S1002 换大一码",
            goal("exchange", target_variant="tee-white-L"),
            fault("restart"),
            None,
        ),
        (
            "cancel-transaction-rollback",
            "取消订单 S1001",
            goal("cancel", "S1001"),
            fault("before_commit"),
            {"operation_count": 0, "refund_count": 0},
        ),
        (
            "return-transaction-rollback",
            "S1002 退货",
            goal("return"),
            fault("before_commit"),
            {"operation_count": 0, "application_count": 0},
        ),
        (
            "exchange-transaction-rollback",
            "S1002 换大一码",
            goal("exchange", target_variant="tee-white-L"),
            fault("before_commit"),
            {
                "operation_count": 0,
                "application_count": 0,
                "inventory": {"tee-white-L": {"available": 1, "reserved": 0}},
            },
        ),
        (
            "cancel-shipped-after-preview",
            "取消订单 S1001",
            goal("cancel", "S1001"),
            fault("ship_order", order_id="S1001"),
            {"operation_count": 0, "refund_count": 0},
        ),
        (
            "stock-race",
            "S1002 换大一码",
            goal("exchange", target_variant="tee-white-L"),
            fault("inventory_zero", variant_id="tee-white-L"),
            {"operation_count": 0, "application_count": 0},
        ),
    ]:
        no_commit = exp is not None
        # Fault rejection or rollback is a safe outcome.
        # The oracle requires no receipt, never a fake success.
        if no_commit:
            expected = {
                "operation_count": 0,
                "application_count": 0,
                "refund_count": 0,
                "handoff_count": 0,
                **exp,
            }
            add(
                "recovery",
                family,
                text,
                {**g, "accept": False} if f["kind"] == "before_commit" else g,
                faults=[f],
                expected=expected,
                communications=[],
            )
            # A before_commit fault needs a genuine approval to exercise the transaction.
            CASES[-1].hidden_user_goal.pop("accept", None)
            for k in ("action", "result", "target_variant", "quantity", "order_id"):
                CASES[-1].expected_state_invariants.pop(k, None)
        else:
            add("recovery", family, text, g, faults=[f])
    for family, text, g, key in [
        (
            "duplicate-cancel-confirm",
            "取消订单 S1001",
            goal("cancel", "S1001"),
            "repeat_confirmation",
        ),
        ("duplicate-return-confirm", "S1002 退货", goal("return"), "repeat_confirmation"),
        (
            "duplicate-exchange-confirm",
            "S1002 换大一码",
            goal("exchange", target_variant="tee-white-L"),
            "repeat_confirmation",
        ),
        ("duplicate-client-message", "S1002 退货", goal("return"), "repeat_message"),
    ]:
        add("recovery", family, text, g, steps=[{"on": "preview", key: 2}])
    assert len(CASES) == 60
    path = Path(__file__).with_name("scenarios.jsonl")
    path.write_text("\n".join(c.model_dump_json() for c in CASES) + "\n")


if __name__ == "__main__":
    build()
