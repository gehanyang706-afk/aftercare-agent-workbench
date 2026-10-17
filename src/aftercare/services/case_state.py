"""Effective facts are versioned by user messages; raw messages remain untouched."""

from copy import deepcopy

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from aftercare.domain.rules import require
from aftercare.repositories.models import Message, Preview


class CaseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int
    source_message_id: str
    changes: dict = Field(default_factory=dict)


ALLOWED = {
    "current_order_id",
    "current_line_id",
    "intent",
    "constraints",
    "missing_fields",
    "evidence_refs",
    "active_preview_id",
}


def update_case(service, principal, conversation_id, request: CaseUpdate):
    require(set(request.changes) <= ALLOWED, "CASE_FIELD_FORBIDDEN")
    with service.sessions.begin() as s:
        conv = service._conversation(s, principal, conversation_id)
        require(conv.revision == request.expected_revision, "INTENT_CHANGED")
        source = s.get(Message, request.source_message_id)
        require(
            source is not None
            and source.conversation_id == conv.id
            and source.role == "user"
            and source.revision == conv.revision,
            "INVALID_FACT_SOURCE",
        )
        case = deepcopy(conv.case or {})
        facts = case.setdefault("facts", {})
        superseded = case.setdefault("superseded", [])
        object_changed = any(
            k in request.changes and facts.get(k, {}).get("value") != request.changes[k]
            for k in ["current_order_id", "current_line_id", "intent"]
        )
        if (
            "current_order_id" in request.changes
            and facts.get("current_order_id", {}).get("value")
            != request.changes["current_order_id"]
            and "current_line_id" in facts
        ):
            superseded.append({"field": "current_line_id", **facts.pop("current_line_id")})
        if object_changed:
            for key in ["constraints", "evidence_refs", "active_preview_id", "missing_fields"]:
                if key in facts:
                    superseded.append({"field": key, **facts.pop(key)})
        for key, value in request.changes.items():
            if key in facts:
                superseded.append({"field": key, **facts[key]})
            # constraints is a complete replacement, never an unbounded additive summary.
            facts[key] = {"value": value, "source_message_id": source.id, "revision": conv.revision}
        case["intent_revision"] = conv.revision
        conv.case = case
        for row in s.scalars(
            select(Preview).where(
                Preview.conversation_id == conv.id, Preview.status.in_(["PENDING", "CONFIRMED"])
            )
        ):
            row.status = "INVALIDATED"
        service.event(
            s, conv.id, "case_updated", {"revision": conv.revision, "fields": list(request.changes)}
        )
        return deepcopy(case)


def assemble_context(snapshot, evidence, recent=8):
    # Never break tool-call/result pairs: tool transcripts are stored in graph messages,
    # this deterministic business context only includes complete user/assistant messages.
    return {
        "state": snapshot.get("case", {}),
        "intent_revision": snapshot["revision"],
        "recent_messages": [
            {"role": m["role"], "content": m["text"], "id": m["id"]}
            for m in snapshot["messages"][-recent:]
        ],
        "evidence": evidence,
    }
