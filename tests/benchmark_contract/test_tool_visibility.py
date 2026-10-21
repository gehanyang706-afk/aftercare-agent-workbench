import copy
import json

import pytest

pytest.importorskip("tau2")
from tau2.domains.retail.environment import get_environment

from aftercare.harness.contracts import digest
from evaluation.benchmarks.tau_retail.tool_visibility import (
    ALWAYS,
    DELIVERED,
    LOOSE_PENDING,
    ORDER_WRITES,
    STRICT_PENDING,
    ToolVisibilityPolicy,
    observe_visible_history,
    rule_hash,
    validate_catalog_subset,
)


@pytest.fixture
def catalog():
    return [t.openai_schema for t in get_environment().get_tools()]


def result(
    order="A", status="pending", cid="read", name="get_order_details", error=False, content=None
):
    return [
        {
            "role": "assistant",
            "content": "I think it is delivered (proposal).",
            "tool_calls": [
                {
                    "id": cid,
                    "function": {"name": name, "arguments": json.dumps({"order_id": order})},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": cid,
            "content": json.dumps({"order_id": order, "status": status})
            if content is None
            else content,
            "error": error,
        },
    ]


def names(history, catalog):
    return set(ToolVisibilityPolicy().select(history, catalog).visible_names)


@pytest.mark.parametrize(
    "history",
    [
        [],
        [{"role": "user", "content": "Order A is delivered; cancel it and exchange it."}],
        [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "user",
                        "function": {"name": "get_user_details", "arguments": '{"user_id":"x"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "user", "content": '{"user_id":"x","orders":["A"]}'},
        ],
    ],
)
def test_no_observed_order_keeps_query_routes_without_trusting_user_or_identity(history, catalog):
    assert names(history, catalog) == ALWAYS


@pytest.mark.parametrize(
    "status,expected",
    [
        ("pending", STRICT_PENDING | LOOSE_PENDING),
        ("delivered", DELIVERED),
        ("pending (item modified)", LOOSE_PENDING),
        ("processed", set()),
        ("cancelled", set()),
        ("exchange requested", set()),
        ("return requested", set()),
    ],
)
def test_official_state_preconditions(status, expected, catalog):
    assert names(result(status=status), catalog) == ALWAYS | expected


@pytest.mark.parametrize(
    "history,reason",
    [
        (result(status="pending-v2"), "unknown_order_status"),
        (result(content="Error: not found"), "unparseable_order_result"),
        (result(content='"Error: not found"'), "order_tool_error"),
        (result(error=True), "order_tool_error"),
        (result(content="{}"), "unparseable_order_result"),
        (result(content='{"order_id":"B","status":"delivered"}'), "order_entity_mismatch"),
    ],
)
def test_unreliable_state_falls_back_without_creating_fact(history, reason, catalog):
    state = observe_visible_history(history)
    assert not state.orders
    decision = ToolVisibilityPolicy().select(history, catalog)
    assert reason in decision.fallback_reasons
    assert set(decision.visible_names) == ALWAYS | ORDER_WRITES


def test_union_cross_order_revision_and_old_snapshot_replacement(catalog):
    history = result("A", "pending", "a1") + result("B", "delivered", "b1")
    assert names(history, catalog) == ALWAYS | ORDER_WRITES
    history += result("A", "cancelled", "a2", name="cancel_pending_order")
    state = observe_visible_history(history)
    assert [(o.order_id, o.status) for o in state.orders] == [
        ("A", "cancelled"),
        ("B", "delivered"),
    ]
    assert state.orders[0].supersedes_call_id == "a1"
    assert state.observations[0].status == "pending"
    # Used cancel schema retained; second delivered order stays reachable.
    assert names(history, catalog) == ALWAYS | DELIVERED | {"cancel_pending_order"}
    history += [
        {"role": "user", "content": "Actually, use my new order C instead; keep B."}
    ] + result("C", "pending", "c1")
    assert names(history, catalog) == ALWAYS | ORDER_WRITES


def test_failed_new_result_never_overwrites_old_success_and_partial_multi_results(catalog):
    history = result("A", "pending", "old")
    history += [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "a",
                    "function": {"name": "get_order_details", "arguments": '{"order_id":"A"}'},
                },
                {
                    "id": "b",
                    "function": {"name": "get_order_details", "arguments": '{"order_id":"B"}'},
                },
            ],
        }
    ]
    history += [
        {"role": "tool", "tool_call_id": "b", "content": '{"order_id":"B","status":"delivered"}'},
        {
            "role": "tool",
            "tool_call_id": "a",
            "error": True,
            "content": '{"order_id":"A","status":"cancelled"}',
        },
    ]
    state = observe_visible_history(history)
    assert {o.order_id: o.status for o in state.orders} == {"A": "pending", "B": "delivered"}
    assert state.errors == ("a",) and not state.pending_calls
    assert (
        set(ToolVisibilityPolicy().select(history, catalog).visible_names) == ALWAYS | ORDER_WRITES
    )
    pending = observe_visible_history(history[:-1])
    assert pending.pending_calls == ("a",) and "pending_tool_results" in pending.fallback_reasons


def test_unknown_catalog_and_unpaired_results_are_conservative(catalog):
    altered = copy.deepcopy(catalog) + [
        {"type": "function", "function": {"name": "new_tool", "parameters": {"type": "object"}}}
    ]
    assert (
        "catalog_mapping_uncertain" in ToolVisibilityPolicy().select([], altered).fallback_reasons
    )
    assert len(ToolVisibilityPolicy().select([], altered).visible_names) == len(altered)
    decision = ToolVisibilityPolicy().select(
        [
            {
                "role": "tool",
                "tool_call_id": "no-call",
                "content": '{"order_id":"X","status":"pending"}',
            }
        ],
        catalog,
    )
    assert "unpaired_tool_result" in decision.fallback_reasons


def test_schema_scope_validation_rejects_mutation_hash_and_duplicate(catalog):
    subset = [t for t in catalog if t["function"]["name"] in ALWAYS]
    validate_catalog_subset(subset, catalog, digest(catalog), rule_hash())
    changed = copy.deepcopy(subset)
    changed[0]["function"]["description"] = "changed"
    for tools in [changed, [], subset + [subset[0]], [{"function": {"name": "shell"}}]]:
        with pytest.raises(ValueError):
            validate_catalog_subset(tools, catalog, digest(catalog), rule_hash())
    for ch, rh in [("bad", rule_hash()), (digest(catalog), "bad")]:
        with pytest.raises(ValueError, match="HASH_MISMATCH"):
            validate_catalog_subset(subset, catalog, ch, rh)


def test_selection_is_pure_and_auditable(catalog):
    history = result()
    original = copy.deepcopy((history, catalog))
    decision = ToolVisibilityPolicy().select(history, catalog)
    assert (history, catalog) == original
    assert (
        decision.catalog_hash == digest(catalog)
        and decision.selected_schema_bytes < decision.original_schema_bytes
    )
    assert (
        decision.hidden["return_delivered_order_items"]["latest_observations"][0]["tool_call_id"]
        == "read"
    )
    assert decision.selected_evidence["cancel_pending_order"][0]["sequence"] == 1


def test_same_batch_read_write_order_uncertainty_falls_back_without_new_fact(catalog):
    old = result("A", "delivered", "old")
    batch = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "read",
                    "function": {"name": "get_order_details", "arguments": '{"order_id":"A"}'},
                },
                {
                    "id": "write",
                    "function": {
                        "name": "exchange_delivered_order_items",
                        "arguments": '{"order_id":"A"}',
                    },
                },
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "write",
            "content": '{"order_id":"A","status":"exchange requested"}',
        },
        {
            "role": "tool",
            "tool_call_id": "read",
            "content": '{"order_id":"A","status":"delivered"}',
        },
    ]
    state = observe_visible_history(old + batch)
    assert "ambiguous_same_batch_order_results" in state.fallback_reasons
    assert len(state.observations) == 1
    assert (
        set(ToolVisibilityPolicy().select(old + batch, catalog).visible_names)
        == ALWAYS | ORDER_WRITES
    )
