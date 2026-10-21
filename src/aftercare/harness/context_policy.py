"""Pure policies: never execute/cache tools or invent facts; raw inputs are immutable."""

from copy import deepcopy

from aftercare.harness.contracts import PreparedContext, canonical, digest
from aftercare.harness.message_blocks import message_blocks


def compact_json_whitespace(text):
    """Validate JSON, then preserve every lexeme, duplicate key and string byte.

    Parsing is only a validity check, never a serialization source. Malformed and
    non-JSON tool text is left untouched by the caller.
    """
    import json

    def invalid_constant(value):
        raise ValueError("NON_JSON_CONSTANT:" + value)

    json.loads(text, parse_float=str, parse_int=str, parse_constant=invalid_constant)
    result, quoted, escaped = [], False, False
    for char in text:
        if quoted:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
            result.append(char)
        elif char not in " \t\r\n":
            result.append(char)
    return "".join(result)


class ContextPolicy:
    def __init__(self, policy_id="full_history", window=8):
        if policy_id not in {"full_history", "fixed_window", "evidence_projection"}:
            raise ValueError("UNKNOWN_CONTEXT_POLICY")
        self.policy_id, self.window = policy_id, window

    def build(self, context, context_limit):
        blocks = message_blocks(deepcopy(context.visible_history))
        selections, selected = [], []
        for index, block in enumerate(blocks):
            keep, reason = True, "full_visible_history"
            if self.policy_id == "fixed_window":
                keep = index >= len(blocks) - self.window
                reason = "whole_block_window" if keep else "outside_window"
            projected = deepcopy(block)
            if self.policy_id == "evidence_projection":
                # Lossless JSON whitespace normalization only. Unknown tool schemas, errors,
                # money, IDs, options, snapshots and every user revision stay fully visible.
                reason = "lossless_json_normalization"
                for message in projected:
                    if message.get("role") == "tool" and isinstance(message.get("content"), str):
                        try:
                            message["content"] = compact_json_whitespace(message["content"])
                        except (ValueError, TypeError):
                            pass
            selections.append(
                {
                    "block": index,
                    "kept": keep,
                    "reason": reason,
                    "source_hash": digest(block),
                    "prepared_hash": digest(projected),
                    "source_bytes": len(canonical(block).encode()),
                    "prepared_bytes": len(canonical(projected).encode()) if keep else 0,
                    "observations": [
                        deepcopy(o)
                        for o in context.source_observations
                        if o.get("tool_call_id")
                        in {m.get("tool_call_id") for m in block if m.get("role") == "tool"}
                    ],
                    "provenance": [
                        "tool_observation"
                        if m.get("role") == "tool"
                        else "user_evidence"
                        if m.get("role") == "user"
                        else "model_proposal"
                        for m in block
                    ],
                }
            )
            if keep:
                selected.extend(projected)
        messages = [{"role": "system", "content": context.full_policy}, *selected]
        size = len(canonical({"messages": messages, "tools": context.tools}).encode())
        if size > context_limit:
            raise ValueError("CONTEXT_LIMIT_NO_SAFE_COMPRESSION")
        return PreparedContext(messages, selections, size, self.policy_id)
