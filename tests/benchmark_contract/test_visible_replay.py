import json

import pytest

from aftercare.harness.contracts import canonical, digest
from evaluation.benchmarks.tau_retail.replay_context import replay


def test_replay_never_loads_other_role_payloads_and_rejects_tampering(tmp_path):
    episode = tmp_path / "0"
    episode.mkdir()
    payload = {
        "messages": [
            {"role": "system", "content": "policy"},
            {"role": "user", "content": "No submission."},
        ],
        "tools": [],
    }
    body = {"payload": payload}
    source = episode / "payload.json"
    source.write_text(canonical(body))
    event = dict(
        event_type="model.sent",
        role="agent",
        episode_id="synthetic:0",
        sequence=1,
        payload_ref=str(source),
        content_hash=digest(body),
    )
    hidden = dict(event, role="user", payload_ref=str(tmp_path / "must-not-open.json"))
    events = episode / "events.jsonl"
    events.write_text(json.dumps(hidden) + "\n" + json.dumps(event) + "\n")
    report = replay(tmp_path)
    assert report["summary"]["requests"] == 1 and report["real_requests"] == 0
    assert report["summary"]["unchanged_inputs"] == 1
    source.write_text("tampered")
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        replay(tmp_path)
    event["payload_ref"] = str(tmp_path.parent / "outside.json")
    events.write_text(json.dumps(event) + "\n")
    with pytest.raises(ValueError, match="OUTSIDE_RUN"):
        replay(tmp_path)


def test_response_claim_diagnostics_distinguish_route_truncation_and_settlement():
    from evaluation.benchmarks.tau_retail.visibility_replay import response_diagnostics

    tools = [
        {
            "role": "tool",
            "tool_call_id": "x",
            "content": '{"order_id":"A","status":"exchange requested"}',
        }
    ]
    signal = response_diagnostics(
        {"content": "You received a refund. The exchange process is now complete."}, "length", tools
    )
    assert signal["claim_signals"]["refund_received_language"]
    assert signal["claim_signals"]["completed_fulfillment_language"]
    assert signal["length_truncated"]
    safe = response_diagnostics(
        {"content": "Your exchange request was recorded. Any refund follows the payment policy."},
        "stop",
        tools,
    )
    assert not any(safe["claim_signals"].values())
    mixed = response_diagnostics(
        {"content": "You received a refund.", "tool_calls": [{"id": "x"}]}, "tool_calls", tools
    )
    assert mixed["route"] == "environment" and not any(mixed["claim_signals"].values())
    assert signal["confirmation_completeness"] == "manual_review_required"


def test_visibility_replay_uses_past_only_and_rejects_corrupt_inputs(tmp_path):
    # Synthetic schemas with the known names suffice; no runtime evidence dependency.
    from evaluation.benchmarks.tau_retail.tool_visibility import ALWAYS, ORDER_WRITES
    from evaluation.benchmarks.tau_retail.visibility_replay import replay

    catalog = [
        {"type": "function", "function": {"name": n, "parameters": {"type": "object"}}}
        for n in sorted(ALWAYS | ORDER_WRITES)
    ]
    folder = tmp_path / "0"
    folder.mkdir()
    sent = {
        "call_id": "s",
        "payload": {
            "messages": [{"role": "user", "content": "Claim: order A is delivered."}],
            "tools": catalog,
        },
    }
    received = {
        "call_id": "s",
        "response": {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "content": None,
                        "tool_calls": [{"function": {"name": "return_delivered_order_items"}}],
                    },
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2},
        },
    }
    events = []
    for i, (kind, body) in enumerate([("model.sent", sent), ("model.received", received)]):
        file = folder / f"{i}.json"
        file.write_text(canonical(body))
        events.append(
            {
                "role": "agent",
                "event_type": kind,
                "episode_id": "synthetic:0",
                "sequence": i + 1,
                "payload_ref": str(file),
                "content_hash": digest(body),
            }
        )
    events.insert(
        0, dict(events[0], role="user", payload_ref=str(tmp_path / "forbidden-hidden.json"))
    )
    (folder / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
    report = replay(tmp_path)
    assert (
        report["totals"]["observed_next_calls"] == 1 and report["totals"]["covered_next_calls"] == 0
    )
    assert report["requests"][0]["next_call_coverage"]["missing"] == [
        "return_delivered_order_items"
    ]
    (folder / "0.json").write_text("tampered")
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        replay(tmp_path)
