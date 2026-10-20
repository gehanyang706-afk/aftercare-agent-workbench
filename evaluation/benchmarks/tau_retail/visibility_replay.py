"""Offline replay: choose from past visible messages before inspecting next response.

User/judge inputs and evaluator payloads are never opened. Diagnostic patterns are
signals for human review, not a model judge or a replacement official reward.
"""

import argparse
import hashlib
import json
import re
from collections import Counter
from copy import deepcopy
from pathlib import Path

from aftercare.harness.contracts import canonical, digest
from evaluation.benchmarks.tau_retail.tool_visibility import ToolVisibilityPolicy


def load_verified(root, event):
    path = Path(event["payload_ref"]).resolve()
    if not path.is_relative_to(root):
        raise ValueError("PAYLOAD_OUTSIDE_RUN")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != event["content_hash"]:
        raise ValueError("PAYLOAD_HASH_MISMATCH")
    return json.loads(raw)


def response_diagnostics(message, finish_reason, visible_messages):
    text = message.get("content") or ""
    mixed = bool(message.get("tool_calls"))
    # This is the upstream default routing, not a claim that mixed text reached user.
    user_facing = not mixed
    patterns = {
        "refund_received_language": (
            r"(?:you (?:have )?received a refund|refund (?:has |was )?(?:arrived|credited)|"
            r"refund.{0,30}already.{0,20}(?:account|received))"
        ),
        "completed_fulfillment_language": (
            r"(?:exchange process is now complete|exchanges? (?:is|are) now complete|"
            r"items? (?:has|have) (?:arrived|been delivered))"
        ),
    }
    successful_results = []
    for m in visible_messages:
        if m.get("role") != "tool":
            continue
        try:
            value = json.loads(m.get("content") or "")
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict) and value.get("order_id") and value.get("status"):
            successful_results.append(
                {
                    "tool_call_id": m.get("tool_call_id"),
                    "status": value["status"],
                    "content_hash": digest(m.get("content")),
                }
            )
    return {
        "finish_reason": finish_reason,
        "length_truncated": finish_reason == "length",
        "content_characters": len(text),
        "long_explanation_signal": len(text) > 2000,
        "route": "environment" if mixed else "user",
        "claim_signals": {
            name: bool(user_facing and re.search(pattern, text, flags=re.I))
            for name, pattern in patterns.items()
        },
        "successful_order_observations": successful_results,
        "confirmation_completeness": "manual_review_required",
        "redundant_question": "manual_review_required",
        "note": "Incomplete signals, not semantic scoring; no bank settlement is inferred.",
    }


def replay(run_dir, profile_path=None):
    root = Path(run_dir).resolve()
    expected = json.loads(Path(profile_path).read_text()) if profile_path else None
    verified = {}
    if expected:
        for name, sha in expected["verified_files"].items():
            path = (root / name).resolve()
            if (
                not path.is_relative_to(root)
                or hashlib.sha256(path.read_bytes()).hexdigest() != sha
            ):
                raise ValueError("REFERENCE_PROFILE_INPUT_MISMATCH")
        # Only hashes above; role-restricted contents below.
    records, decisions, inputs, responses, components, fallback, tool_names = (
        [],
        {},
        {},
        {},
        Counter(),
        Counter(),
        Counter(),
    )
    totals = Counter()
    for event_file in sorted(root.glob("*/events.jsonl")):
        verified[str(event_file.relative_to(root))] = hashlib.sha256(
            event_file.read_bytes()
        ).hexdigest()
        for line in event_file.read_text().splitlines():
            event = json.loads(line)
            if event.get("role") != "agent" or event["event_type"] not in {
                "model.sent",
                "model.received",
            }:
                continue
            body = load_verified(root, event)
            verified[str(Path(event["payload_ref"]).resolve().relative_to(root))] = event[
                "content_hash"
            ]
            cid = body["call_id"]
            if event["event_type"] == "model.sent":
                payload = body["payload"]
                before = deepcopy(payload)
                decision = ToolVisibilityPolicy().select(payload["messages"], payload["tools"])
                routed = deepcopy(payload)
                routed["tools"] = [
                    t for t in payload["tools"] if t["function"]["name"] in decision.visible_names
                ]
                assert payload == before and routed["messages"] == payload["messages"]
                totals["requests"] += 1
                totals["original_bytes"] += len(canonical(payload).encode())
                totals["routed_bytes"] += len(canonical(routed).encode())
                components["tool_schema"] += len(canonical(payload["tools"]).encode())
                for message in payload["messages"]:
                    components[message["role"] + "_content"] += len(
                        canonical(message.get("content")).encode()
                    )
                    if message["role"] == "assistant" and message.get("tool_calls"):
                        components["assistant_tool_calls"] += len(
                            canonical(message["tool_calls"]).encode()
                        )
                fallback.update(decision.fallback_reasons)
                record = {
                    "episode": event["episode_id"],
                    "sequence": event["sequence"],
                    "call_id": cid,
                    "payload_hash": digest(payload),
                    "routed_hash": digest(routed),
                    "original_bytes": len(canonical(payload).encode()),
                    "routed_bytes": len(canonical(routed).encode()),
                    "decision": decision.to_dict(),
                }
                records.append(record)
                decisions[cid] = record
                inputs[cid] = payload["messages"]
            else:
                if cid not in decisions:
                    raise ValueError("RESPONSE_WITHOUT_PRIOR_DECISION")
                response = body["response"]
                choice = response["choices"][0]
                names = [c["function"]["name"] for c in choice["message"].get("tool_calls") or []]
                tool_names.update(names)
                missing = [n for n in names if n not in decisions[cid]["decision"]["visible_names"]]
                totals["observed_next_calls"] += len(names)
                totals["covered_next_calls"] += len(names) - len(missing)
                decisions[cid]["next_call_coverage"] = {"names": names, "missing": missing}
                usage = response["usage"]
                totals["actual_agent_input_tokens"] += usage["prompt_tokens"]
                totals["actual_agent_output_tokens"] += usage["completion_tokens"]
                responses[cid] = response_diagnostics(
                    choice["message"], choice["finish_reason"], inputs[cid]
                )
    components["other_framing"] = totals["original_bytes"] - sum(components.values())
    if expected:
        et = expected["totals"]
        for actual, key in [
            ("requests", "requests"),
            ("original_bytes", "request_bytes"),
            ("actual_agent_input_tokens", "actual_agent_input_tokens"),
            ("actual_agent_output_tokens", "actual_agent_output_tokens"),
            ("observed_next_calls", "observed_tool_calls"),
        ]:
            if totals[actual] != et[key]:
                raise ValueError("REFERENCE_PROFILE_TOTAL_MISMATCH:" + actual)
        if any(components[k] != v["bytes"] for k, v in expected["request_components"].items()):
            raise ValueError("REFERENCE_PROFILE_COMPONENT_MISMATCH")
    totals["byte_reduction_percent"] = (
        100 * (1 - totals["routed_bytes"] / totals["original_bytes"])
        if totals["original_bytes"]
        else 0
    )
    return {
        "version": "visibility-replay-v1",
        "real_requests": 0,
        "totals": dict(totals),
        "request_components": dict(components),
        "fallback_counts": dict(fallback),
        "observed_tool_counts": dict(tool_names),
        "requests": records,
        "response_diagnostics": responses,
        "verified_files": verified,
        "reference_profile_matched": bool(expected),
        "limitations": [
            "Bytes are not provider Tokens.",
            "Coverage uses historical next calls, never the full legal action space.",
            "Claim and redundancy checks require human review, not a new judge.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--profile")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    from aftercare.offline import install_offline_guard

    install_offline_guard()
    report = replay(args.run_dir, args.profile)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {k: report[k] for k in ["totals", "fallback_counts", "reference_profile_matched"]},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
