"""Clarification process observations, never authorization or frozen score changes.

This conservative recognizer reports quantity-only redundancy. It does not claim
all natural-language questions can be classified, nor infer missing user facts.
"""

import re

from aftercare.services.intent_guard import user_evidence
from evaluation.evaluator.diagnostics_v3 import diagnose as receipt_diagnose
from evaluation.evaluator.diagnostics_v3 import event_chain

VERSION = "process-diagnostic-v4"
__all__ = ["VERSION", "diagnose", "event_chain"]


def diagnose(observed):
    base = receipt_diagnose(observed)
    users, redundant = [], []
    for event in observed.get("events", []):
        payload = event["payload"]
        if event["event_type"] == "user_message":
            users.append({"id": payload["message_id"], "text": payload["text"]})
        if event["event_type"] != "user_notice" or payload.get("stage") != "clarification":
            continue
        evidence = user_evidence(users)
        if evidence.get("quantity") is None:
            continue
        text = re.sub(r"[*_`#]", "", payload.get("text", ""))
        asks_quantity = bool(re.search(r"几件|多少件|件数|数量[^。\n]{0,30}[？?]", text))
        repeats_quantity = bool(
            re.search(r"确认|对吗", text)
            and re.search(r"(?:换货|退货|申请|本次)?数量[：:\s]*\d+\s*件", text)
        )
        if asks_quantity or repeats_quantity:
            redundant.append(
                {
                    "notice_event_id": event.get("id"),
                    "quantity": evidence["quantity"],
                    "source_message_id": evidence.get("quantity_source"),
                    "text": payload["text"],
                }
            )
    return {**base, "version": VERSION, "redundant_quantity_clarifications": redundant}
