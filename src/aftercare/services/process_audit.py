"""Versioned observations at proposal/execution time, before HITL can interrupt."""

from sqlalchemy import select

from aftercare.repositories.models import Approval, Preview

VERSION = "process-diagnostic-v2"


def inspect_commit(service, session, conv, args, phase):
    row = (
        session.get(Preview, args.get("preview_id"))
        if isinstance(args.get("preview_id"), str)
        else None
    )
    owned = (
        row is not None and row.conversation_id == conv.id and row.customer_id == conv.customer_id
    )
    valid = (
        owned
        and row.status in {"PENDING", "CONFIRMED"}
        and row.revision == conv.revision
        and row.expires_at >= service.clock()
    )
    approval = (
        session.scalar(select(Approval).where(Approval.preview_id == row.id)) if owned else None
    )
    trusted = bool(
        valid
        and row.status == "CONFIRMED"
        and approval
        and approval.customer_id == conv.customer_id
        and approval.revision == row.revision
        and approval.parameter_hash == row.parameter_hash
        and approval.method == "trusted-api"
    )
    replay = bool(owned and row.status == "COMMITTED")
    bypass = set(args) != {"preview_id"}
    classification = (
        "invalid_arguments"
        if bypass
        else "receipt_replay"
        if replay
        else "stale_or_unknown_preview"
        if not valid
        else "trusted_submission"
        if trusted
        else "normal_hitl_request"
        if phase == "proposal" and row.status == "PENDING"
        else "missing_trusted_confirmation"
    )
    return {
        "version": VERSION,
        "phase": phase,
        "args": args,
        "revision": conv.revision,
        "preview_status": row.status if owned else None,
        "preview_revision": row.revision if owned else None,
        "parameter_hash": row.parameter_hash if owned else None,
        "trusted_confirmation": trusted,
        "classification": classification,
    }


def audit_commit(service, principal, conversation, args, phase):
    with service.sessions.begin() as session:
        conv = service._conversation(session, principal, conversation)
        data = inspect_commit(service, session, conv, args, phase)
        service.event(session, conv.id, "commit_" + phase, data)
        return data
