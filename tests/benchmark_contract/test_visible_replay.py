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
