"""Append-only local audit, hash-addressed payloads; never publish raw tasks."""

import json
import time
from pathlib import Path

from aftercare.harness.contracts import canonical, digest


class Trace:
    def __init__(self, root, run_id, episode_id, variant, trial=0):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.meta = dict(run_id=run_id, episode_id=episode_id, variant=variant, trial=trial)
        self.path = self.root / "events.jsonl"
        self.sequence = sum(1 for _ in self.path.open()) if self.path.exists() else 0

    def emit(self, event_type, payload, role="agent", **relations):
        content_hash = digest(payload)
        store = self.root / "payloads"
        store.mkdir(exist_ok=True)
        path = store / (content_hash + ".json")
        if not path.exists():
            with path.open("x") as f:
                f.write(canonical(payload))
            path.chmod(0o600)
        self.sequence += 1
        event = dict(
            schema_version="retail-trace-v2",
            **self.meta,
            role=role,
            sequence=self.sequence,
            monotonic_time=time.monotonic(),
            event_type=event_type,
            parent_id=None,
            message_id=None,
            tool_call_id=None,
            payload_ref=str(path),
            content_hash=content_hash,
        )
        event.update(relations)
        with self.path.open("a") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        self.path.chmod(0o600)
        return event


def attach_environment_trace(environment, trace):
    """Observe the official execution entry once; never substitute a result or cache tools."""
    original = environment.get_response
    state = {
        "mutation_sequence": 0,
        "reads": set(),
        "executed": 0,
        "repeated_reads": 0,
        "seconds": 0,
    }

    def observed(call):
        started = time.monotonic()
        is_read = not environment._is_mutating_tool(call.name)
        key = (call.name, canonical(call.arguments), state["mutation_sequence"])
        repeated = is_read and key in state["reads"]
        result = original(call)
        elapsed = time.monotonic() - started
        state["executed"] += 1
        state["seconds"] += elapsed
        state["repeated_reads"] += repeated
        if is_read and not result.error:
            state["reads"].add(key)
        elif not is_read:
            # Conservative invalidation even for a failed/partially unknown write.
            state["mutation_sequence"] += 1
        trace.emit(
            "tool.failed" if result.error else "tool.completed",
            {
                "result": result.model_dump(mode="json"),
                "seconds": elapsed,
                "mutation_sequence": state["mutation_sequence"],
                "is_read": is_read,
                "repeated_read": repeated,
            },
            tool_call_id=call.id,
        )
        return result

    environment.get_response = observed
    return state
