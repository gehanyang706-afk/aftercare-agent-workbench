"""Server-persisted confirmation events; a status string is never an execution permit."""

from sqlalchemy import select

from aftercare.domain.rules import require
from aftercare.repositories.models import Approval, Event, Preview
from aftercare.services.business import columns, digest

FIELDS = ("preview_id", "principal", "parameter_hash", "intent_revision", "decision")


def latest_event(service, principal, conversation, preview_id):
    with service.sessions.begin() as s:
        service._conversation(s, principal, conversation)
        rows = s.scalars(
            select(Event)
            .where(
                Event.conversation_id == conversation,
                Event.event_type.in_(["preview_confirmed", "preview_rejected"]),
            )
            .order_by(Event.id.desc())
        )
        for row in rows:
            if row.payload.get("preview_id") == preview_id and all(
                k in row.payload for k in FIELDS
            ):
                return {**{k: row.payload[k] for k in FIELDS}, "event_id": row.id}
    return None


def validate(service, principal, conversation, binding):
    require(
        isinstance(binding, dict) and set(binding) == set(FIELDS) | {"event_id"},
        "CONFIRMATION_EVENT_REQUIRED",
    )
    with service.sessions.begin() as s:
        conv = service._conversation(s, principal, conversation)
        event = s.get(Event, binding["event_id"])
        require(
            event is not None
            and event.conversation_id == conversation
            and event.event_type in {"preview_confirmed", "preview_rejected"},
            "CONFIRMATION_EVENT_INVALID",
        )
        require(
            all(event.payload.get(k) == binding.get(k) for k in FIELDS),
            "CONFIRMATION_BINDING_MISMATCH",
        )
        row = s.get(Preview, binding["preview_id"])
        require(
            row is not None
            and row.customer_id == principal
            and row.conversation_id == conversation
            and binding["principal"] == principal,
            "CONFIRMATION_BINDING_MISMATCH",
        )
        require(
            row.parameter_hash == binding["parameter_hash"]
            and row.revision == binding["intent_revision"]
            and conv.revision == row.revision,
            "INTENT_CHANGED",
        )
        require(
            digest({k: v for k, v in row.payload.items() if k != "computed"}) == row.parameter_hash,
            "PARAMETER_HASH_MISMATCH",
        )
        if binding["decision"] == "reject":
            require(
                row.status == "REJECTED" and event.event_type == "preview_rejected",
                "CONFIRMATION_EVENT_INVALID",
            )
        else:
            require(
                binding["decision"] == "approve" and event.event_type == "preview_confirmed",
                "CONFIRMATION_EVENT_INVALID",
            )
            approval = s.get(Approval, row.id)
            require(
                approval is not None
                and approval.method == "trusted-api"
                and approval.customer_id == principal
                and approval.parameter_hash == row.parameter_hash
                and approval.revision == row.revision,
                "APPROVAL_REQUIRED",
            )
            if row.status != "COMMITTED":
                service._valid_preview(conv, row)
                require(row.status == "CONFIRMED", "APPROVAL_REQUIRED")
        return columns(row)
