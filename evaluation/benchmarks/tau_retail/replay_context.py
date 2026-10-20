"""Offline visible-agent payload replay. Never load user/judge inputs or task bodies."""

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path

from aftercare.harness.context_policy import ContextPolicy, compact_json_whitespace
from aftercare.harness.contracts import ContextInput, canonical, digest


def replay(run_dir):
    root = Path(run_dir).resolve()
    report = {"schema": "visible-context-replay-v1", "real_requests": 0, "requests": []}
    for event_file in sorted(root.glob("*/events.jsonl")):
        for line in event_file.read_text().splitlines():
            event = json.loads(line)
            if event["event_type"] != "model.sent" or event["role"] != "agent":
                continue
            path = Path(event["payload_ref"]).resolve()
            if not path.is_relative_to(root):
                raise ValueError("PAYLOAD_OUTSIDE_RUN")
            body = path.read_bytes()
            if hashlib.sha256(body).hexdigest() != event["content_hash"]:
                raise ValueError("PAYLOAD_HASH_MISMATCH")
            payload = json.loads(body)["payload"]
            before = deepcopy(payload)
            messages = payload["messages"]
            if messages[0]["role"] != "system":
                raise ValueError("SYSTEM_POLICY_REQUIRED")
            ctx = ContextInput(messages[1:], messages[0]["content"], payload.get("tools", []))
            prepared = ContextPolicy("evidence_projection").build(ctx, 10**9)
            projected = deepcopy(payload)
            projected["messages"] = prepared.messages
            assert len(messages) == len(prepared.messages)
            assert all(s["kept"] for s in prepared.selection_manifest)
            for old, new in zip(messages, prepared.messages, strict=True):
                if old["role"] == "tool" and isinstance(old.get("content"), str):
                    expected = deepcopy(old)
                    try:
                        expected["content"] = compact_json_whitespace(old["content"])
                    except (ValueError, TypeError):
                        pass
                    assert expected == new
                else:
                    assert old == new
            assert payload == before
            report["requests"].append(
                dict(
                    episode=event["episode_id"],
                    sequence=event["sequence"],
                    input_hash=digest(payload),
                    projected_hash=digest(projected),
                    payload_bytes=len(canonical(payload).encode()),
                    projected_bytes=len(canonical(projected).encode()),
                    user_messages_preserved=sum(m["role"] == "user" for m in messages),
                    selections=prepared.selection_manifest,
                )
            )
    rows = report["requests"]
    report["summary"] = dict(
        requests=len(rows),
        original_bytes=sum(r["payload_bytes"] for r in rows),
        projected_bytes=sum(r["projected_bytes"] for r in rows),
        unchanged_inputs=sum(r["input_hash"] == r["projected_hash"] for r in rows),
        note="Byte replay only; no model response, task-success or Token saving prediction.",
    )
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    from aftercare.offline import install_offline_guard

    install_offline_guard()
    result = replay(args.run_dir)
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
