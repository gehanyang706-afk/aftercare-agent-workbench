"""Validate tool-call sets by ID; a multi-call exchange is indivisible."""


def message_blocks(messages):
    blocks, pending, block = [], set(), []
    seen = set()
    for message in messages:
        role = message.get("role")
        if role == "tool":
            call_id = message.get("tool_call_id")
            if call_id not in pending:
                raise ValueError("ORPHAN_OR_DUPLICATE_TOOL_RESULT")
            block.append(message)
            pending.remove(call_id)
            if not pending:
                blocks.append(block)
                block = []
        else:
            if pending:
                raise ValueError("INCOMPLETE_TOOL_BLOCK")
            calls = message.get("tool_calls") or []
            if calls:
                ids = [c["id"] for c in calls]
                if len(set(ids)) != len(ids) or seen.intersection(ids):
                    raise ValueError("DUPLICATE_TOOL_CALL_ID")
                seen.update(ids)
                pending = set(ids)
                block = [message]
            else:
                blocks.append([message])
    if block:
        blocks.append(block)  # Pending calls are legal only at the tail; retain the whole block.
    return blocks
