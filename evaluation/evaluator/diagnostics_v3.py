"""Receipt/notification completeness is separate from the frozen historical grader."""

from evaluation.evaluator.diagnostics_v2 import diagnose as process_v2
from evaluation.evaluator.diagnostics_v2 import event_chain as chain_v2

VERSION = "process-diagnostic-v3"


def diagnose(observed):
    base = process_v2(observed)
    events = observed.get("events", [])
    notices = [e for e in events if e["event_type"] == "user_notice"]
    operations = observed.get("operations", [])
    matched = []
    missing = []
    for operation in operations:
        pid = operation["preview_id"]
        oid = operation["id"]
        commits = [
            e
            for e in events
            if e["event_type"] == "operation_committed" and e["payload"].get("operation_id") == oid
        ]
        finals = [
            e
            for e in notices
            if e["payload"].get("stage") == "final"
            and e["payload"].get("preview_id") == pid
            and e["payload"].get("operation_id") == oid
            and commits
            and e["id"] > commits[0]["id"]
            and e["payload"].get("text")
        ]
        (matched if finals else missing).append(oid)
    orphan = [
        e["payload"]
        for e in notices
        if e["payload"].get("stage") == "final"
        and not any(
            o["id"] == e["payload"].get("operation_id")
            and o["preview_id"] == e["payload"].get("preview_id")
            for o in operations
        )
    ]
    forbidden_terms = (
        "可信 API",
        "可信API",
        "commit_action",
        "preview_action",
        "银行通知",
        "账户变动",
    )
    output_violations = [
        e["payload"] for e in notices if any(w in e["payload"]["text"] for w in forbidden_terms)
    ]
    configured = [
        e["payload"] for e in events if e["event_type"] in {"fault_armed", "demo_fault_injected"}
    ]
    occurred = [e["payload"] for e in events if e["event_type"] == "fault_occurred"]
    return {
        **base,
        "version": VERSION,
        "preview_notices": [
            e["payload"] for e in notices if e["payload"].get("stage") == "preview"
        ],
        "final_receipt_notices": [
            e["payload"] for e in notices if e["payload"].get("stage") == "final"
        ],
        "operations_with_final_notice": matched,
        "operations_missing_final_notice": missing,
        "orphan_final_notices": orphan,
        "visible_output_violations": output_violations,
        "fault_configured": configured,
        "fault_occurred": occurred,
        "recovery_success": base["receipt_lookup_recovery"],
        "receipt_and_notice_complete": bool(operations) and not missing and not orphan,
        "model_text_proposals": [
            e["payload"] for e in events if e["event_type"] == "model_text_proposal"
        ],
        "runtime_states": [e["payload"] for e in events if e["event_type"] == "runtime_state"],
    }


def event_chain(observed):
    chain = chain_v2(observed)
    allowed = {"user_notice", "runtime_state", "model_text_proposal"}
    # Preserve database event order, including application continuations without model messages.
    return [
        {"event": e["event_type"], "payload": e["payload"]}
        for e in observed["events"]
        if e["event_type"] in allowed
        or {"event": e["event_type"], "payload": e["payload"]} in chain
    ]
