"""Requested counts must remain separate from purchase, retention and alternatives."""

import pytest

from aftercare.services.intent_guard import explicit_quantity, user_evidence


@pytest.mark.parametrize(
    "text,expected",
    [
        ("其中一件", 1),
        ("全部两件", 2),
        ("只退一件，另一件保留", 1),
        ("买了两件，想退其中一件", 1),
        ("买了2件想退1件", 1),
        ("退两件，另外一件保留", 2),
        ("两件中的一件换大一码", 1),
        ("不是两件，改成一件", 1),
        ("不要退两件，只退一件", 1),
        ("购买数量两件，申请数量一件", 1),
        ("数量：两件", 2),
        ("S1002 换大一码", None),
        ("订单购买两件", None),
        ("库存只有一件", None),
        ("另一件保留", None),
        ("保留两件", None),
        ("一件还是两件", None),
        ("大概两件", None),
        ("一两件", None),
        ("不是一件", None),
        ("两件不要退", None),
        ("不换一件了", None),
        ("十一件", None),
    ],
)
def test_quantity_interpretation(text, expected):
    assert explicit_quantity(text) == expected


def evidence(*texts):
    return user_evidence([{"id": f"m{i}", "text": t} for i, t in enumerate(texts)])


@pytest.mark.parametrize("followup", ["不是一件", "数量没想好", "一件还是两件", "不换了，改为退货"])
def test_ambiguous_or_changed_request_clears_previous_quantity(followup):
    assert "quantity" not in evidence("S1002 换其中一件", followup)


def test_quantity_reply_preserves_order_action_and_new_source():
    got = evidence("S1002 换大一码", "其中一件")
    assert got == {
        "order_id": "S1002",
        "action": "exchange",
        "quantity": 1,
        "quantity_source": "m1",
    }


def test_other_item_retention_does_not_change_request():
    got = evidence("S1002 退两件", "另外一件保留")
    assert got["quantity"] == 2 and got["action"] == "return"


def test_new_order_does_not_inherit_quantity():
    assert "quantity" not in evidence("S1002 换一件", "改为 S1003 换大一码")


def test_multiple_orders_and_actions_are_not_one_authorized_count():
    assert "quantity" not in evidence("S1002 退一件，S1003 退一件")
    assert "quantity" not in evidence("S1002 退一件再换一件")


def test_purchase_count_does_not_supply_request_count():
    assert "quantity" not in evidence("S1002 买了两件，想换大一码")


def test_explicit_revision_replaces_prior_request():
    got = evidence("S1002 换两件", "不换了，改为退其中一件，另一件保留")
    assert got["action"] == "return" and got["quantity"] == 1


@pytest.mark.parametrize(
    "text,expected",
    [
        ("订单 S1002 中 1 件换大一码", 1),
        ("订单有两件，想换大一码", None),
        ("退1-2件", None),
        ("买两件其中一件退货", 1),
    ],
)
def test_order_context_does_not_erase_explicit_request_or_supply_default(text, expected):
    assert explicit_quantity(text) == expected


def test_another_item_without_count_does_not_reuse_prior_requested_count():
    assert "quantity" not in evidence("S1002 换两件", "换另一件")


@pytest.mark.parametrize(
    "text", ["不想退两件", "不打算换一件", "不用退一件", "别换两件", "两件不想退", "全部退货"]
)
def test_negated_or_non_numeric_all_count_is_not_authority(text):
    assert explicit_quantity(text) is None


def test_plain_action_change_preserves_explicit_same_order_quantity_but_not_cancellation():
    kept = evidence("S1002 换其中一件", "改成退货")
    assert kept["quantity"] == 1 and kept["action"] == "return"
    assert "quantity" not in evidence("S1002 换其中一件", "不想换了，改为退货")
    assert "quantity" not in evidence("S1002 换其中一件", "改为全部退货")


def test_cancelled_request_count_does_not_leak_across_later_action_change():
    assert "quantity" not in evidence("S1002 换一件", "不换了", "改退货")
