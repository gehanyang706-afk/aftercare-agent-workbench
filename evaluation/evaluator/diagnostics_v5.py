"""Quantity process review is separate from frozen state/communication scoring."""

import re

from aftercare.services.intent_guard import user_evidence
from evaluation.evaluator.diagnostics_v4 import diagnose as previous_diagnose
from evaluation.evaluator.diagnostics_v4 import event_chain as previous_chain

VERSION = "process-diagnostic-v5"


def diagnose(observed):
    base = previous_diagnose(observed)
    events = observed.get("events", [])
    proposals, rejected, replies, no_submit, users = [], [], [], [], []
    preview_created_after_reply = False
    for event in events:
        payload, kind = event["payload"], event["event_type"]
        if kind == "user_message":
            users.append({"id": payload["message_id"], "text": payload["text"]})
            if re.search(r"暂不提交|暂不办理|不要办理|停止办理", payload["text"]):
                no_submit.append(payload)
            if user_evidence(users).get("quantity_source") == payload["message_id"]:
                replies.append(event["id"])
        elif kind == "quantity_tool_proposal":
            proposals.append({"event_id": event["id"], **payload})
        elif kind == "tool_result" and payload.get("result", {}).get("error_code") in {
            "QUANTITY_CLARIFICATION_REQUIRED",
            "CASE_QUANTITY_MISMATCH",
        }:
            rejected.append({"event_id": event["id"], **payload})
        elif kind == "preview_created":
            trusted = user_evidence(users).get("quantity")
            preview_created_after_reply |= bool(
                payload["payload"].get("quantity") == trusted
                and any(
                    p["evidence_status"] != "MATCH" and p["event_id"] < reply < event["id"]
                    for p in proposals
                    for reply in replies
                )
            )
    unsupported = [p for p in proposals if p["evidence_status"] != "MATCH"]
    return {
        **base,
        "version": VERSION,
        "quantity_tool_proposals": proposals,
        "unsupported_quantity_proposals": unsupported,
        "preview_proposals_before_quantity_evidence": [
            p for p in proposals if p["tool"] == "preview_action" and p["trusted_quantity"] is None
        ],
        "backend_quantity_rejections": rejected,
        "quantity_clarification_recovered": bool(unsupported and preview_created_after_reply),
        "quantity_process_clean": not unsupported,
        "quantity_proposal_coverage": "instrumented" if proposals else "no_quantity_proposals",
        "user_no_submit_messages": no_submit,
        "no_submit_honored": bool(no_submit) and not observed.get("operations"),
        "model_execution_stops": [
            e["payload"] for e in events if e["event_type"] == "model_execution_stopped"
        ],
    }


def event_chain(observed):
    chain = previous_chain(observed)
    allowed = {"quantity_tool_proposal", "model_execution_stopped"}
    return [
        {"event": e["event_type"], "payload": e["payload"]}
        for e in observed.get("events", [])
        if e["event_type"] in allowed
        or {"event": e["event_type"], "payload": e["payload"]} in chain
    ]
