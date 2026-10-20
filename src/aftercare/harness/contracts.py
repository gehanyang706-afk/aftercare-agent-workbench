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
