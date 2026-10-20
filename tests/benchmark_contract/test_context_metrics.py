import copy

import pytest

from aftercare.harness.context_policy import ContextPolicy
from aftercare.harness.contracts import ContextInput
from aftercare.harness.message_blocks import message_blocks
from evaluation.benchmarks.tau_retail.metrics import repeated_reads, summarize


def history():
    result = []
    for i in range(12):
        result += [
            {"role": "user", "content": f"order {i}; change quantity to 2; cancel prior choice"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"a{i}",
                        "type": "function",
                        "function": {"name": "get", "arguments": "{}"},
                    },
                    {
                        "id": f"b{i}",
                        "type": "function",
                        "function": {"name": "write", "arguments": "{}"},
                    },
                ],
            },
            {"role": "tool", "tool_call_id": f"b{i}", "content": '{ "error": "OUT_OF_STOCK" }'},
            {
                "role": "tool",
                "tool_call_id": f"a{i}",
                "content": (
                    '{ "price": 12.5, "payment": "p1", "options": [1,2], '
                    '"address": "a", "status": "new" }'
                ),
            },
        ]
    return result


@pytest.mark.parametrize("policy", ["full_history", "fixed_window", "evidence_projection"])
def test_context_keeps_protocol_whole_policy_raw_immutable(policy):
    raw = history()
    original = copy.deepcopy(raw)
    prepared = ContextPolicy(policy).build(
        ContextInput(raw, "FULL POLICY", [{"name": "get"}]), 999999
    )
    assert raw == original
    assert prepared.messages[0]["content"] == "FULL POLICY"
    message_blocks(prepared.messages[1:])
    if policy != "fixed_window":
        assert len([m for m in prepared.messages if m["role"] == "user"]) == 12
        assert "OUT_OF_STOCK" in str(prepared.messages)
        assert "payment" in str(prepared.messages)
    with pytest.raises(ValueError, match="CONTEXT_LIMIT"):
        ContextPolicy(policy).build(ContextInput(raw, "FULL POLICY", []), 10)


def test_pending_and_duplicate_tool_ids():
    assert message_blocks(history()[:2])
    broken = history()[:3] + [history()[2]]
    with pytest.raises(ValueError, match="ORPHAN_OR_DUPLICATE"):
        message_blocks(broken)


def row(task, variant, reward=1, tokens=100, unknown=0, status="completed"):
    return dict(
        experiment_version="v1",
        trial=0,
        task_id=task,
        variant=variant,
        official_reward=reward,
        status=status,
        roles={
            "agent": dict(known_tokens=tokens, unknown_reserved=unknown),
            "user": dict(known_tokens=999),
        },
    )


def test_metrics_negative_early_failure_unknown_partial():
    rows = [
        row("x", "a", 1, 100),
        row("x", "b", 1, 150),
        row("y", "a", 1, 100),
        row("y", "b", 0, 1),
    ]
    m = summarize(rows)
    assert m["paired"]["success_delta_pp"] == -50
    assert m["paired"]["both_success_agent_token_saving_pct"] == -50
    assert m["variants"]["a"]["roles"]["agent"]["known_tokens"] == 200
    rows[1]["roles"]["agent"]["unknown_reserved"] = 10
    assert summarize(rows)["paired"]["agent_token_saving_pct"] is None
    rows[1]["status"], rows[1]["official_reward"] = "not_run", None
    assert summarize(rows)["coverage"]["b"]["not_run"] == 1
    assert summarize(rows)["paired"]["success_delta_pp"] is None
    with pytest.raises(ValueError, match="DUPLICATE"):
        summarize(rows + rows)
    other = copy.deepcopy(rows)
    other[1]["trial"] = 1
    with pytest.raises(ValueError, match="MIXED"):
        summarize(other)


def test_repeated_read_is_not_stale_across_write():
    events = [
        dict(name="get", canonical_arguments="{}", mutation_sequence=n, is_read=True)
        for n in (0, 0, 1)
    ]
    assert repeated_reads(events) == 1


def test_official_baseline_is_denominator_even_when_lexical_order_differs():
    rows = [row("x", "official_tc", 1, 100), row("x", "harness_evidence", 1, 150)]
    assert summarize(rows)["paired"]["variant_order"] == ["official_tc", "harness_evidence"]
    assert summarize(rows)["paired"]["agent_token_saving_pct"] == -50
    rows[1]["roles"].pop("agent")
    assert summarize(rows)["paired"]["agent_token_saving_pct"] is None


def test_observations_have_sources_and_writes_invalidate_without_deleting_history():
    from aftercare.harness.contracts import observations

    raw = history()
    obs = observations(raw, {"get": False, "write": True})
    assert obs[0]["tool_call_id"] == "b0"
    assert obs[1]["tool_call_id"] == "a0"
    assert obs[1]["freshness"] == "historical_after_mutation"
    assert obs[-1]["observed_sequence"] == len(raw) - 1
    prepared = ContextPolicy("evidence_projection").build(
        ContextInput(raw, "policy", [], obs), 999999
    )
    assert prepared.selection_manifest[1]["observations"]
    assert len(prepared.messages) == len(raw) + 1
