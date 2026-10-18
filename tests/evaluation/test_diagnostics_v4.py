"""Distilled first-run redundant clarifications and contrasting legitimate questions."""

import pytest

from evaluation.evaluator.diagnostics_v4 import diagnose


def observed(user, reply, stage="clarification"):
    return {
        "events": [
            {"id": 1, "event_type": "user_message", "payload": {"message_id": "m", "text": user}},
            {"id": 2, "event_type": "user_notice", "payload": {"stage": stage, "text": reply}},
        ]
    }


@pytest.mark.parametrize(
    "reply",
    [
        "您希望将其中 **1 件** 换成大一码，对吗？\n本次换货数量是 **1 件**？",
        "您想将其中 **1 件** 换为大一码，对吗？\n请确认以下信息：\n- 换货数量：1 件",
        "请问本次需要换几件？",
    ],
)
def test_known_quantity_reconfirmation_is_reported(reply):
    d = diagnose(observed("订单 S1002 中 1 件换大一码", reply))
    assert len(d.get("redundant_quantity_clarifications", [])) == 1


@pytest.mark.parametrize(
    "user,reply,stage",
    [
        ("S1002 换大一码", "请问本次换几件？", "clarification"),
        ("我买了 2 件，想换大一码", "请问本次换几件？", "clarification"),
        ("S1002 中 1 件换大一码", "库存不足，请选择是否等待？", "clarification"),
        ("S1002 中 1 件换大一码", "请确认换货方案，数量 1 件？", "preview"),
    ],
)
def test_missing_quantity_stock_choice_and_transaction_confirmation_are_distinct(
    user, reply, stage
):
    d = diagnose(observed(user, reply, stage))
    assert not d.get("redundant_quantity_clarifications", [])


def test_new_order_does_not_inherit_prior_quantity():
    data = observed("S1002 中 1 件换大一码", "请问本次换几件？")
    data["events"].insert(
        1,
        {
            "id": 2,
            "event_type": "user_message",
            "payload": {"message_id": "m2", "text": "改为 S1003 换大一码"},
        },
    )
    data["events"][-1]["id"] = 3
    assert not diagnose(data).get("redundant_quantity_clarifications", [])
