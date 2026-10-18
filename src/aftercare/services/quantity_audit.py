"""Conservative assertion diagnostic; never a grading or authorization rule."""

import re

from aftercare.services.intent_guard import explicit_quantity


def quantity_claims(text, evidence):
    # A question/example is not an assertion of a user requirement.
    claims = []
    for sentence in re.split(r"[。！\n]", text):
        if any(w in sentence for w in ("？", "?", "例如", "请问", "几件", "多少件")):
            continue
        qty = explicit_quantity(sentence)
        if qty is not None and re.search(
            r"(您|你|用户).{0,18}(申请|要求|希望|想|要|换|退)", sentence
        ):
            if qty != evidence.get("quantity"):
                claims.append(
                    {
                        "text": sentence,
                        "quantity": qty,
                        "trusted_quantity": evidence.get("quantity"),
                    }
                )
    return claims


def quantity_proposal(tool, args, evidence):
    """Observe model parameters before execution, including rejected preview attempts."""
    if tool == "preview_action":
        values = args
    elif tool == "update_case":
        changes = args.get("changes") or {}
        values = changes.get("constraints") or {} if isinstance(changes, dict) else {}
    else:
        return None
    if not isinstance(values, dict) or "quantity" not in values:
        return None
    proposed, trusted = values["quantity"], evidence.get("quantity")
    status = (
        "UNKNOWN"
        if trusted is None
        else "MATCH"
        if type(proposed) is int and proposed == trusted
        else "MISMATCH"
    )
    target_order = (
        args.get("order_id")
        if tool == "preview_action"
        else (args.get("changes") or {}).get("current_order_id")
    )
    if target_order and target_order != evidence.get("order_id"):
        status = "ORDER_MISMATCH"
    return {
        "proposed_order_id": target_order,
        "trusted_order_id": evidence.get("order_id"),
        "version": "quantity-proposal-v1",
        "tool": tool,
        "proposed_quantity": proposed,
        "trusted_quantity": trusted,
        "source_message_id": evidence.get("quantity_source"),
        "evidence_status": status,
    }
