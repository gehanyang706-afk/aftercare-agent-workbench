from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from aftercare.domain.contracts import ActionInput, BusinessError
from aftercare.repositories.models import (
    Application,
    Event,
    Inventory,
    Operation,
    Order,
    OrderLine,
    Policy,
    Preview,
    Refund,
    Reservation,
)
from aftercare.services.demo import settle_application, ship_order


def action(kind="exchange", order="S1002", target="tee-white-L", **extra):
    return ActionInput(
        action=kind,
        order_id=order,
        line_id=order + "-1" if kind != "cancel" else None,
        target_variant=target if kind == "exchange" else None,
        **extra,
    )


def prepared(service, value=None, owner="alice", approved=True):
    conv = service.create_conversation(owner)
    preview = service.preview(owner, conv, value or action())
    if approved:
        service.confirm(owner, preview["id"], True)
    return conv, preview["id"]


def error(code, call):
    with pytest.raises(BusinessError) as e:
        call()
    assert e.value.code == code


@pytest.mark.parametrize(
    "kind,order,result",
    [
        ("cancel", "S1001", "CANCELLED"),
        ("return", "S1002", "RETURN_REQUESTED"),
        ("exchange", "S1002", "EXCHANGE_REQUESTED"),
    ],
)
def test_normal_transactions_and_receipts(service, kind, order, result):
    _, pid = prepared(service, action(kind, order))
    receipt = service.commit("alice", pid)
    assert receipt["result"] == result
    assert service.get_operation("alice", preview_id=pid) == receipt
    with service.sessions() as s:
        assert s.scalar(select(func.count()).select_from(Operation)) == 1
        if kind == "cancel":
            assert s.get(Order, order).status == "CANCELLED"
            assert s.scalar(select(Refund)).amount_fen == 19800
        else:
            assert s.get(Order, order).status == "DELIVERED"
            assert s.get(Application, receipt["application_id"]).status == result
            assert s.get(OrderLine, order + "-1").occupied == 1


def test_cross_principal_and_no_approval(service):
    _, pid = prepared(service, approved=False)
    error("APPROVAL_REQUIRED", lambda: service.commit("alice", pid))
    error("NOT_FOUND", lambda: service.confirm("bob", pid, True))
    error("NOT_FOUND", lambda: service.get_order("alice", "S2001"))


def test_message_dedup_and_old_confirm_invalidation(service):
    conv, pid = prepared(service)
    first = service.append_message("alice", conv, "改成退货", "client1")
    assert service.append_message("alice", conv, "改成退货", "client1") == first
    error("MESSAGE_ID_CONFLICT", lambda: service.append_message("alice", conv, "其他", "client1"))
    error("PREVIEW_INVALIDATED", lambda: service.confirm("alice", pid, True))
    error("PREVIEW_INVALIDATED", lambda: service.commit("alice", pid))


def test_parallel_repeat_and_alias_idempotency(service):
    _, pid = prepared(service)
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(lambda _: service.commit("alice", pid), range(2)))
    assert receipts[0] == receipts[1]
    assert service.commit("alice", pid, "another-key") == receipts[0]
    _, other = prepared(service, action("cancel", "S1001"))
    error("IDEMPOTENCY_CONFLICT", lambda: service.commit("alice", other, "another-key"))
    with service.sessions() as s:
        assert s.scalar(select(func.count()).select_from(Application)) == 1
        assert s.get(Inventory, "tee-white-L").available == 0
        assert s.get(Inventory, "tee-white-L").reserved == 1


def test_two_customers_compete_for_one_inventory(service):
    _, one = prepared(service)
    _, two = prepared(service, action(order="S2001"), owner="bob")

    def call(pair):
        try:
            return service.commit(*pair)["status"]
        except BusinessError as e:
            return e.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(call, [("alice", one), ("bob", two)]))
    assert sorted(results) == ["COMMITTED", "STATE_CHANGED"]
    with service.sessions() as s:
        stock = s.get(Inventory, "tee-white-L")
        assert (stock.available, stock.reserved) == (0, 1)
        assert s.scalar(select(func.count()).select_from(Application)) == 1


def test_rollback_covers_application_stock_operation_event(service):
    conv, pid = prepared(service)
    with service.sessions() as s:
        before = s.scalar(select(func.count()).select_from(Event))
    with pytest.raises(RuntimeError, match="INJECTED_TRANSACTION_FAILURE"):
        service.commit("alice", pid, fault="before_commit")
    with service.sessions() as s:
        assert s.scalar(select(func.count()).select_from(Application)) == 0
        assert s.scalar(select(func.count()).select_from(Operation)) == 0
        assert s.scalar(select(func.count()).select_from(Event)) == before
        assert s.get(Inventory, "tee-white-L").available == 1
        assert s.get(Preview, pid).status == "CONFIRMED"
    assert service.commit("alice", pid)["status"] == "COMMITTED"


def test_lost_response_recovered_with_same_operation_after_restart(service):
    _, pid = prepared(service)
    error("WRITE_RESULT_UNKNOWN", lambda: service.commit("alice", pid, fault="lost_response"))
    from aftercare.services.business import BusinessService

    restarted = BusinessService(service.sessions, service.clock)
    assert restarted.get_operation("alice", preview_id=pid) == restarted.commit("alice", pid)


def test_shipped_order_rejects_old_cancel_and_quantity_overlap(service):
    _, pid = prepared(service, action("cancel", "S1001"))
    ship_order(service.sessions, "S1001")
    error("STATE_CHANGED", lambda: service.commit("alice", pid))
    conv, first = prepared(service, action("return", "S1002", quantity=2))
    service.commit("alice", first)
    error("QUANTITY_UNAVAILABLE", lambda: prepared(service, action("return", "S1002")))


@pytest.mark.parametrize("kind,hours", [("return", 168), ("exchange", 360)])
def test_inclusive_window_boundary_and_one_microsecond_outside(service, kind, hours):
    with service.sessions.begin() as s:
        s.get(Order, "S1002").delivered_at = service.clock() - timedelta(hours=hours)
    _, pid = prepared(service, action(kind))
    assert pid
    with service.sessions.begin() as s:
        s.get(Order, "S1002").delivered_at -= timedelta(microseconds=1)
    error("OUTSIDE_POLICY_WINDOW", lambda: prepared(service, action(kind)))


def test_expiry_policy_change_and_nonreturnable(service):
    _, pid = prepared(service)
    with service.sessions.begin() as s:
        s.get(Preview, pid).expires_at = service.clock() - timedelta(seconds=1)
    error("PREVIEW_EXPIRED", lambda: service.commit("alice", pid))
    _, pid = prepared(service)
    with service.sessions.begin() as s:
        s.get(Policy, "v1").content_hash = "new-policy-hash"
    error("POLICY_CHANGED", lambda: service.commit("alice", pid))
    error("ITEM_INELIGIBLE", lambda: prepared(service, action("return", "S3001"), owner="carol"))


def test_release_and_complete_reservations(service):
    _, pid = prepared(service)
    receipt = service.commit("alice", pid)
    settle_application(service.sessions, receipt["application_id"], "WITHDRAWN")
    settle_application(service.sessions, receipt["application_id"], "WITHDRAWN")
    with service.sessions() as s:
        assert s.get(Inventory, "tee-white-L").available == 1
        assert s.get(Inventory, "tee-white-L").reserved == 0
        assert s.get(OrderLine, "S1002-1").occupied == 0
    _, pid = prepared(service)
    receipt = service.commit("alice", pid)
    settle_application(service.sessions, receipt["application_id"], "COMPLETED")
    with service.sessions() as s:
        assert s.get(Inventory, "tee-white-L").available == 0
        assert s.get(Inventory, "tee-white-L").reserved == 0
        assert s.get(Reservation, receipt["application_id"]).status == "CONSUMED"


def test_preview_replay_and_handoff_dedup(service):
    conv = service.create_conversation("alice")
    one = service.preview("alice", conv, action())
    assert service.preview("alice", conv, action())["id"] == one["id"]
    ticket = service.handoff("alice", conv, "QUALITY_DISPUTE", "质量争议待人工认定")
    assert service.handoff("alice", conv, "QUALITY_DISPUTE", "重复请求")["id"] == ticket["id"]


def test_expired_preview_can_be_regenerated(service):
    conv, pid = prepared(service)
    with service.sessions.begin() as s:
        s.get(Preview, pid).expires_at = service.clock() - timedelta(seconds=1)
    replacement = service.preview("alice", conv, action())
    assert replacement["id"] != pid
    assert replacement["status"] == "PENDING"


def test_confirm_revalidates_order_version(service):
    _, pid = prepared(service, action("cancel", "S1001"), approved=False)
    ship_order(service.sessions, "S1001")
    error("STATE_CHANGED", lambda: service.confirm("alice", pid, True))
