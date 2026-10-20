from sqlalchemy import func, select

from aftercare.repositories.models import (
    Application,
    Approval,
    Inventory,
    Job,
    Message,
    ModelCall,
    Operation,
    Reservation,
)


def snapshot(sessions):
    with sessions() as s:
        counts = {
            model.__tablename__: s.scalar(select(func.count()).select_from(model))
            for model in (Operation, Application, Reservation, Approval, Message, Job, ModelCall)
        }
        stocks = {
            r.variant_id: {"available": r.available, "reserved": r.reserved, "version": r.version}
            for r in s.scalars(select(Inventory))
        }
        receipts = [r.receipt for r in s.scalars(select(Operation))]
        jobs = [
            {
                "id": j.id,
                "owner": j.lease_owner,
                "status": j.status,
                "attempt": j.attempt,
                "result": j.result,
            }
            for j in s.scalars(select(Job))
        ]
        applications = [
            {
                "id": r.id,
                "operation_id": r.operation_id,
                "line_id": r.line_id,
                "quantity": r.quantity,
                "target_variant": r.target_variant,
            }
            for r in s.scalars(select(Application))
        ]
        approvals = [
            {
                "preview_id": r.preview_id,
                "customer_id": r.customer_id,
                "parameter_hash": r.parameter_hash,
                "revision": r.revision,
            }
            for r in s.scalars(select(Approval))
        ]
        reservations = [
            {"application_id": r.application_id, "quantity": r.quantity, "variant_id": r.variant_id}
            for r in s.scalars(select(Reservation))
        ]
        notices = [
            {"id": m.id, "text": m.text, "revision": m.revision}
            for m in s.scalars(select(Message).where(Message.role == "assistant"))
        ]
    return dict(
        counts=counts,
        inventory=stocks,
        receipts=receipts,
        jobs=jobs,
        notices=notices,
        applications=applications,
        approvals=approvals,
        reservations=reservations,
    )


def unique_exchange(state, expected=1):
    counts = state["counts"]
    assert (
        counts["operations"]
        == counts["aftercare_requests"]
        == counts["inventory_reservations"]
        == expected
    )
    stock = state["inventory"]["tee-white-L"]
    assert stock["available"] == 1 - expected and stock["reserved"] == expected
    assert all(v["available"] >= 0 and v["reserved"] >= 0 for v in state["inventory"].values())
