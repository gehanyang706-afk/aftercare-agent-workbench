"""Serializable, benchmark-independent visible-context contracts. No task/oracle fields."""

import hashlib
import json
from dataclasses import dataclass, field


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


@dataclass(frozen=True)
class ContextInput:
    visible_history: list[dict]
    full_policy: str
    tools: list[dict]
    source_observations: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class PreparedContext:
    messages: list[dict]
    selection_manifest: list[dict]
    estimated_size: int
    policy_id: str


def observations(history, mutates_state):
    """Derive provenance from visible call/result pairs, never from a model summary.

    Unknown tools conservatively create a mutation barrier. Entity bindings name the
    request target; only raw result hashes are observations, arguments remain proposals.
    """
    import json

    calls, output, epoch = {}, [], 0
    for sequence, message in enumerate(history):
        for call in message.get("tool_calls") or []:
            fn = call.get("function", {})
            arguments = fn.get("arguments", {})
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except ValueError:
                    arguments = {}
            calls[call["id"]] = (fn.get("name"), arguments)
        if message.get("role") != "tool":
            continue
        cid = message.get("tool_call_id")
        name, args = calls.get(cid, (None, {}))
        mutation = mutates_state.get(name, True)
        if mutation:
            epoch += 1
            for previous in output:
                previous["freshness"] = "historical_after_mutation"
        entities = {k: v for k, v in args.items() if k.endswith("_id") and isinstance(v, str)}
        content = message.get("content")
        current = dict(
            tool_call_id=cid,
            tool_name=name,
            request_entities=entities,
            observed_sequence=sequence,
            mutation_epoch=epoch,
            content_hash=digest(content),
            freshness="visible_observation",
        )
        if entities and not mutation:
            for previous in output:
                if previous["tool_name"] == name and previous["request_entities"] == entities:
                    previous["freshness"] = "historical_superseded_snapshot"
        output.append(current)
    return output
