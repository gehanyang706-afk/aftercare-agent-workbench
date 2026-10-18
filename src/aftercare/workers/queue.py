from sqlalchemy import select

from aftercare.repositories.models import Conversation, Job
from aftercare.services.business import new_id


def enqueue(s, service, conversation, revision, kind, message_id=None, preview_id=None):
    dedup = "message:" + message_id if message_id else f"{kind}:{preview_id}"
    existing = s.scalar(select(Job).where(Job.dedup_key == dedup))
    if existing:
        return existing.id
    row = Job(
        id=new_id("job"),
        conversation_id=conversation,
        message_id=message_id,
        dedup_key=dedup,
        kind=kind,
        revision=revision,
        status="PENDING",
        lease_owner=None,
        lease_expires_at=None,
        attempt=0,
        cancel_requested=False,
        result={},
        created_at=service.clock(),
    )
    if preview_id:
        from aftercare.repositories.models import Preview

        preview = s.get(Preview, preview_id)
        binding = getattr(preview, "confirmation_event", None)
        if binding is None:
            raise ValueError("CONFIRMATION_EVENT_REQUIRED")
        row.result = {"confirmation": binding}
    conv = s.get(Conversation, conversation)
    fault = conv.case.get("_demo_fault_next")
    if fault and (kind == "confirm" or fault == "slow"):
        row.result = {**row.result, "fault": fault}
        updated = dict(conv.case)
        updated.pop("_demo_fault_next", None)
        conv.case = updated
    s.add(row)
    s.flush()
    service.event(
        s, conversation, "job_queued", {"job_id": row.id, "kind": kind, "revision": revision}
    )
    return row.id
