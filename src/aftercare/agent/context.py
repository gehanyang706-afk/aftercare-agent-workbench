"""Deterministic tool-result projection; originals remain in checkpoints and audit rows."""

import json

from langchain_core.messages import ToolMessage


def case_model_context(snapshot):
    from aftercare.services.intent_guard import user_evidence

    evidence = user_evidence([m for m in snapshot.get("messages", []) if m["role"] == "user"])
    return {
        "facts": {
            key: {"value": fact.get("value"), "provenance": "model_proposal"}
            for key, fact in snapshot.get("case", {}).get("facts", {}).items()
        },
        "user_quantity_evidence": {
            "quantity": evidence.get("quantity"),
            "source_message_id": evidence.get("quantity_source"),
        },
    }


def keep(value, fields):
    return {key: item for key, item in value.items() if key in fields}


def project_tool_result(message):
    if not isinstance(message, ToolMessage):
        return message
    try:
        result = json.loads(str(message.content))
        if not result.get("ok"):
            return message
        data = result.get("data")
        name = message.name
        if name == "update_case":
            data = {"intent_revision": data.get("intent_revision"), "status": "updated"}
        elif name == "search_policies":
            data = [keep(row, {"policy_ref", "title", "text", "content_hash"}) for row in data]
        elif name == "list_orders":
            data = [
                keep(row, {"id", "status", "paid_fen", "delivered_at", "policy_version"})
                for row in data
            ]
        elif name == "get_inventory":
            data = [
                keep(
                    row,
                    {
                        "id",
                        "product_id",
                        "color",
                        "size",
                        "price_fen",
                        "available",
                        "returnable",
                        "exchangeable",
                    },
                )
                for row in data
            ]
        elif name == "get_order":
            data = {
                **keep(data, {"id", "status", "paid_fen", "delivered_at", "policy_version"}),
                "lines": [
                    {
                        **keep(row, {"id", "quantity", "occupied", "unused"}),
                        "variant": keep(
                            row["variant"],
                            {
                                "id",
                                "product_id",
                                "color",
                                "size",
                                "price_fen",
                                "returnable",
                                "exchangeable",
                                "category",
                            },
                        ),
                    }
                    for row in data["lines"]
                ],
            }
        elif name == "preview_action":
            data = keep(data, {"id", "status", "payload", "revision", "expires_at"})
        result = {"ok": True, "data": data}
        return message.model_copy(
            update={"content": json.dumps(result, ensure_ascii=False, separators=(",", ":"))}
        )
    except (ValueError, TypeError, KeyError, AttributeError):
        return message


def assemble_messages(messages):
    from langchain_core.messages import HumanMessage

    starts = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
    current = starts[-1] if starts else 0
    kept = []
    for position, begin in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(messages)
        block = messages[begin:end]
        committed = False
        for item in block:
            if isinstance(item, ToolMessage) and item.name in {"commit_action", "get_operation"}:
                try:
                    result = json.loads(str(item.content))
                    committed |= bool(
                        result.get("ok") and result.get("data", {}).get("status") == "COMMITTED"
                    )
                except (ValueError, AttributeError):
                    pass
        kept.extend(block if begin == current or committed else [messages[begin]])
    messages = kept if starts else messages
    current = max((i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), default=0)
    preview = None
    preview_call_id = None
    for message in messages[current:]:
        if isinstance(message, ToolMessage) and message.name == "preview_action":
            try:
                result = json.loads(str(message.content))
                if result.get("ok"):
                    preview = result["data"]["id"]
                    preview_call_id = message.tool_call_id
            except (ValueError, KeyError, TypeError):
                pass
    if preview_call_id:
        start = next(
            (
                i
                for i, item in enumerate(messages)
                if i > current
                and any(
                    call.get("id") == preview_call_id for call in getattr(item, "tool_calls", [])
                )
            ),
            None,
        )
        if start is not None:
            # Replace intermediate reads with the validated preview, keeping its whole call block.
            # Previous committed receipt blocks and raw user messages remain intact.
            messages = messages[: current + 1] + messages[start:]
    reads = {"update_case", "list_orders", "get_order", "get_inventory", "search_policies"}
    output = []
    for index, message in enumerate(messages):
        projected = project_tool_result(message)
        if (
            isinstance(message, ToolMessage)
            and message.name in reads
            and (index < current or preview)
        ):
            try:
                result = json.loads(str(projected.content))
                if result.get("ok"):
                    data = (
                        {"historical": True} if index < current else {"validated_preview": preview}
                    )
                    if message.name == "search_policies" and index >= current:
                        data["policy_refs"] = [row["policy_ref"] for row in result["data"]]
                    projected = projected.model_copy(
                        update={
                            "content": json.dumps(
                                {**result, "data": data}, ensure_ascii=False, separators=(",", ":")
                            )
                        }
                    )
            except (ValueError, KeyError, TypeError):
                pass
        output.append(projected)
    return output
