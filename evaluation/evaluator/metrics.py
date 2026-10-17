"""Explicit task-level denominators; unavailable measurements stay unavailable."""

import math
import statistics


def metrics(results, cases):
    rejected = []
    eligible = []
    unauthorized = 0
    wrong_effects = 0
    fields, retained = 0, 0
    for row, case in zip(results, cases, strict=True):
        expected = case.expected_state_invariants
        observed = row["observed"]
        (eligible if expected.get("operation_count", 0) > 0 else rejected).append(row)
        unauthorized += any(
            name
            in {"unauthorized_commit_attempt", "forbidden_tool_attempt", "invalid_tool_attempt"}
            for name in row["result"]["process_failures"]
        )
        wrong = len(observed["operations"]) > expected.get("operation_count", 0)
        for operation in observed["operations"]:
            payload = next(
                p["payload"] for p in observed["previews"] if p["id"] == operation["preview_id"]
            )
            wrong |= any(
                payload.get(k) != expected[k]
                for k in ("order_id", "action", "target_variant", "quantity")
                if k in expected
            )
        wrong_effects += bool(wrong)
        if case.category == "revision":
            updates = [
                e["payload"]["result"].get("data", {})
                for e in observed["events"]
                if e["event_type"] == "tool_result"
                and e["payload"].get("tool") == "update_case"
                and e["payload"]["result"].get("ok")
            ]
            facts = updates[-1].get("facts", {}) if updates else {}
            for source, key in (("order_id", "current_order_id"), ("action", "intent")):
                if source in case.hidden_user_goal and case.hidden_user_goal.get("action") in {
                    "cancel",
                    "return",
                    "exchange",
                }:
                    fields += 1
                    retained += facts.get(key, {}).get("value") == case.hidden_user_goal[source]
    latency = sorted(r["latency_seconds"] for r in results)
    return {
        "unauthorized_attempt_tasks": {"n": unauthorized, "N": len(results)},
        "wrong_actual_side_effect_tasks": {"n": wrong_effects, "N": len(results)},
        "expected_rejection_or_no_write_success": {
            "n": sum(r["result"]["success"] for r in rejected),
            "N": len(rejected),
        },
        "unnecessary_handoff_on_eligible": {
            "n": sum(bool(r["observed"]["handoffs"]) for r in eligible),
            "N": len(eligible),
        },
        "revision_effective_order_and_intent_fields": {"n": retained, "N": fields},
        "latency_end_to_end_seconds": {
            "median": statistics.median(latency) if latency else None,
            "p95": latency[math.ceil(len(latency) * 0.95) - 1] if latency else None,
            "note": (
                "Includes actor startup; scripted user has no human waiting. "
                "Small-sample P95 is not a production claim."
            ),
        },
        "real_model_tokens_and_cost": None,
        "repeated_task_stability": None,
        "model_retrieval_tool_latency_segments": None,
        "recall_at_5": "Separate 12-question retrieval-dev report; not business success",
    }
