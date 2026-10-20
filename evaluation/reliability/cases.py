"""Real database/process cases. Never use the demo DB; all subprocesses are owned here."""

import multiprocessing as mp
import os
import signal
import time

from sqlalchemy import select, text

from aftercare.config import Settings
from aftercare.domain.contracts import ActionInput, BusinessError, utc_now
from aftercare.repositories.database import session_factory
from aftercare.repositories.models import Base, Conversation, Customer, Job, Order, OrderLine
from aftercare.services.business import BusinessService
from aftercare.services.demo import seed
from aftercare.workers.queue import enqueue
from evaluation.reliability.barriers import Probe, process_birth
from evaluation.reliability.invariants import snapshot, unique_exchange

CTX = mp.get_context("spawn")
TEST_URL = "postgresql+psycopg://aftercare:aftercare_local_only@127.0.0.1:55432/aftercare_test"


def connect(url=TEST_URL):
    sessions = session_factory(Settings(_env_file=None, database_url=url, app_env="test"))
    if sessions.kw["bind"].url.database != "aftercare_test":
        raise ValueError("RELIABILITY_TEST_DATABASE_REQUIRED")
    return sessions


def reset(sessions):
    if sessions.kw["bind"].url.database != "aftercare_test":
        raise ValueError("RELIABILITY_TEST_DATABASE_REQUIRED")
    with sessions.begin() as s:
        names = ", ".join('"' + t.name + '"' for t in Base.metadata.sorted_tables)
        s.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    seed(sessions, utc_now)


def prepare(service, owner="alice", order="S1002", job=False):
    conv = service.create_conversation(owner)
    preview = service.preview(
        owner,
        conv,
        ActionInput(
            action="exchange",
            order_id=order,
            line_id=order + "-1",
            quantity=1,
            target_variant="tee-white-L",
        ),
    )
    callback = (
        (lambda s, c, p: enqueue(s, service, c.id, c.revision, "confirm", preview_id=p.id))
        if job
        else None
    )
    event = service.confirm(owner, preview["id"], True, enqueue=callback)
    return conv, preview["id"], event


def _business_actor(url, kind, params, channel):
    sessions = connect(url)
    service = BusinessService(sessions)
    try:
        channel.send(
            {
                "event": "ready",
                "pid": os.getpid(),
                "started_at": time.time(),
                "process_started_at": process_birth(os.getpid()),
            }
        )
        assert channel.recv() == "release"
        try:
            if kind == "message":
                principal, conv = params
                result = service.append_message(
                    principal,
                    conv,
                    "S1002中1件换货",
                    "same",
                    enqueue=lambda s, m: enqueue(
                        s, service, conv, m.revision, "message", message_id=m.id
                    ),
                )
            elif kind == "confirm_commit":
                principal, pid = params
                service.confirm(principal, pid, True)
                result = service.commit(principal, pid)
            else:
                result = service.commit(*params)
            channel.send({"event": "result", "ok": True, "result": result, "pid": os.getpid()})
        except BusinessError as e:
            channel.send({"event": "result", "ok": False, "error": e.code, "pid": os.getpid()})
    finally:
        sessions.kw["bind"].dispose()
        channel.close()


def concurrent(url, kind, params):
    processes = []
    evidence = []
    channels = []
    try:
        for args in params:
            parent, child = CTX.Pipe()
            p = CTX.Process(target=_business_actor, args=(url, kind, args, child))
            p.start()
            child.close()
            processes.append(p)
            channels.append(parent)
        for channel in channels:
            assert channel.poll(20), "ACTOR_NOT_READY"
            evidence.append(channel.recv())
        for channel in channels:
            channel.send("release")
        results = []
        for channel in channels:
            assert channel.poll(20), "ACTOR_RESULT_TIMEOUT"
            results.append(channel.recv())
        for p in processes:
            p.join(5)
            assert p.exitcode == 0
        return results, evidence
    finally:
        for p in processes:
            if p.is_alive():
                p.kill()
                p.join(3)
        for channel in channels:
            channel.close()


def _worker(url, probe, channel):
    from aftercare.workers.worker import run_once

    try:
        channel.send(
            {
                "event": "worker_start",
                "pid": os.getpid(),
                "started_at": time.time(),
                "process_started_at": process_birth(os.getpid()),
            }
        )
        result = run_once(
            Settings(_env_file=None, database_url=url, app_env="test"),
            seconds=40,
            probe=probe,
            lease_seconds=1,
        )
        channel.send({"event": "worker_exit", "result": result, "pid": os.getpid()})
    except BaseException as e:
        channel.send(
            {"event": "worker_error", "error": type(e).__name__ + ":" + str(e), "pid": os.getpid()}
        )
    finally:
        channel.close()


def start_worker(url, point=None):
    events, child_events = CTX.Pipe()
    barrier, child_barrier = CTX.Pipe()
    p = CTX.Process(
        target=_worker, args=(url, Probe(point, child_barrier) if point else None, child_events)
    )
    p.start()
    child_events.close()
    child_barrier.close()
    assert events.poll(15)
    start = events.recv()
    return p, events, barrier, start


def wait_event(channel, seconds=25):
    assert channel.poll(seconds), "BARRIER_NOT_TRIGGERED"
    return channel.recv()


def wait_expired(sessions, job_id):
    from threading import Event

    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        with sessions() as s:
            row = s.get(Job, job_id)
            if row.lease_expires_at and row.lease_expires_at < utc_now():
                return {"expired_at": row.lease_expires_at.isoformat(), "owner": row.lease_owner}
        Event().wait(0.02)  # Observe real expiry; this does not arrange the fault race.
    raise AssertionError("LEASE_DID_NOT_EXPIRE")


def worker_case(service, case_id):
    from aftercare.agent.runtime import setup_checkpoints
    from aftercare.repositories.models import Operation

    sessions = service.sessions
    url = sessions.kw["bind"].url.render_as_string(hide_password=False)
    setup_checkpoints(Settings(_env_file=None, database_url=url))
    conv, pid, _ = prepare(service, job=True)
    with sessions() as s:
        job_id = s.scalar(select(Job.id).where(Job.conversation_id == conv))
    point = ("after_commit", "before_job_finish") if case_id == "F10" else "before_transaction"
    first = start_worker(url, point)
    second = None
    child_pid = None
    child_birth = None
    evidence = [first[3]]
    try:
        event = wait_event(first[2])
        evidence.append(event)
        child_pid = event["pid"]
        child_birth = event["process_started_at"]
        assert event["ppid"] == first[0].pid, "NOT_A_REAL_EXECUTION_CHILD"
        if case_id == "F10":
            with sessions() as s:
                persisted = s.scalar(select(Operation).where(Operation.preview_id == pid))
                assert persisted and persisted.id == event["operation_id"]
                evidence.append({"commit_verified_independent_connection": persisted.id})
            assert process_birth(child_pid) == child_birth
            os.kill(child_pid, signal.SIGKILL)
            # Observe the parent at finalization, then crash it too. The durable job stays
            # RUNNING; a new process reclaims the genuinely expired lease without DB rewrites.
            parent_finish = wait_event(first[2])
            assert parent_finish["point"] == "before_job_finish"
            evidence.append(parent_finish)
            first[0].kill()
            first[0].join(5)
            evidence.append(wait_expired(sessions, job_id))
            second = start_worker(url)
        else:
            # Kill actual owner while its child is blocked. No manual lease-owner rewrite.
            first[0].kill()
            first[0].join(5)
            os.kill(child_pid, 0)
            evidence.append({"killed_parent": first[0].pid, "surviving_child": child_pid})
            evidence.append(wait_expired(sessions, job_id))
            second = start_worker(url, "after_claim" if case_id == "F11" else None)
            if case_id == "F11":
                takeover = wait_event(second[2])
                evidence.append(takeover)
                with sessions() as s:
                    assert s.get(Job, job_id).lease_owner == takeover["owner"]
                second[2].send("release")
            # New worker acquired owner; old execution resumes and must fail the transaction guard.
            if case_id == "F09":
                from threading import Event

                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    with sessions() as s:
                        if s.get(Job, job_id).attempt >= 2:
                            break
                    Event().wait(0.02)
                else:
                    raise AssertionError("TAKEOVER_NOT_CLAIMED")
            first[2].send("release")
        outcome = wait_event(second[1], 35)
        evidence.append(outcome)
        second[0].join(5)
        assert second[0].exitcode == 0
        final = snapshot(sessions)
        unique_exchange(final)
        assert final["notices"] and final["receipts"][0]["operation_id"] in str(final["notices"])
        if case_id == "F11":
            assert final["jobs"][0]["attempt"] == 2
            assert final["jobs"][0]["status"] == "COMPLETED"
        return {"triggered": True, "evidence": evidence, "state": final}
    except Exception as error:
        error.reliability_evidence = evidence + [{"final_state": snapshot(sessions)}]
        raise
    finally:
        for item in (first, second):
            if item:
                if item[0].is_alive():
                    item[0].kill()
                    item[0].join(3)
                item[1].close()
                item[2].close()
        if child_pid:
            try:
                if process_birth(child_pid) == child_birth:
                    os.kill(child_pid, signal.SIGKILL)
            except (ProcessLookupError, __import__("subprocess").CalledProcessError):
                pass


def run_case(service, case_id):
    sessions = service.sessions
    url = sessions.kw["bind"].url.render_as_string(hide_password=False)
    if case_id in {"F06", "F07"}:
        return linear_case(service, case_id)
    if case_id == "F12":
        return sse_case(service)
    if case_id in {"F09", "F10", "F11"}:
        return worker_case(service, case_id)
    evidence = []
    if case_id == "F01":
        conv = service.create_conversation("alice")
        results, evidence = concurrent(url, "message", [("alice", conv)] * 8)
        assert all(r["ok"] for r in results)
        state = snapshot(sessions)
        assert state["counts"]["messages"] == state["counts"]["jobs"] == 1
        with sessions() as s:
            assert s.get(Conversation, conv).revision == 1
    elif case_id in {"F02", "F03"}:
        _, pid, _ = prepare(service)
        n = 2 if case_id == "F02" else 8
        results, evidence = concurrent(url, "confirm_commit", [("alice", pid)] * n)
        assert all(r["ok"] for r in results)
        assert len({r["result"]["operation_id"] for r in results}) == 1
        state = snapshot(sessions)
        unique_exchange(state)
    elif case_id in {"F04", "F05"}:
        n = 2 if case_id == "F04" else 8
        params = []
        for index in range(n):
            user, order = f"race-{index}", f"race-order-{index}"
            with sessions.begin() as s:
                s.add(Customer(id=user, name=user))
                s.flush()
                original = s.get(Order, "S1002")
                s.add(
                    Order(
                        id=order,
                        customer_id=user,
                        status="DELIVERED",
                        paid_fen=19800,
                        delivered_at=original.delivered_at,
                        version=1,
                        policy_version="v1",
                    )
                )
                s.flush()
                s.add(
                    OrderLine(
                        id=order + "-1",
                        order_id=order,
                        variant_id="tee-black-M",
                        quantity=2,
                        occupied=0,
                        unused=True,
                    )
                )
            _, pid, _ = prepare(service, user, order)
            params.append((user, pid))
        results, evidence = concurrent(url, "commit", params)
        assert sum(r["ok"] for r in results) == 1
        assert all(r["ok"] or r["error"] == "STATE_CHANGED" for r in results)
        state = snapshot(sessions)
        unique_exchange(state)
    elif case_id == "F08":
        # Use the public runtime path with an already-approved preview; it recovers via query.
        from aftercare.agent.runtime import run_turn, setup_checkpoints

        conv, pid, event = prepare(service)
        settings = Settings(_env_file=None, database_url=url)
        setup_checkpoints(settings)
        service.commit_fault = "lost_response"
        result = run_turn(
            settings, service, "alice", conv, resume=True, confirmation=event["confirmation"]
        )
        state = snapshot(sessions)
        unique_exchange(state)
        assert result["receipt"]["preview_id"] == pid and result["notice_saved"]
        from aftercare.repositories.models import Event

        with sessions() as s:
            events = list(s.scalars(select(Event).where(Event.conversation_id == conv)))
            assert any(e.event_type == "fault_occurred" for e in events)
            evidence = [{"event": e.event_type, "payload": e.payload} for e in events]
    else:
        raise ValueError("UNKNOWN_RELIABILITY_CASE")
    return {"triggered": True, "evidence": evidence, "state": state}


def _linear_actor(url, principal, pid, probe, channel):
    sessions = connect(url)
    service = BusinessService(sessions)
    service.commit_probe = probe
    try:
        try:
            result = service.commit(principal, pid)
            channel.send({"ok": True, "receipt": result, "pid": os.getpid()})
        except BusinessError as error:
            channel.send({"ok": False, "error": error.code, "pid": os.getpid()})
    finally:
        sessions.kw["bind"].dispose()
        channel.close()


def linear_case(service, case_id):
    url = service.sessions.kw["bind"].url.render_as_string(hide_password=False)
    conv, pid, _ = prepare(service)
    events, child_events = CTX.Pipe()
    barrier, child_barrier = CTX.Pipe()
    point = "before_transaction" if case_id == "F06" else "after_commit"
    process = CTX.Process(
        target=_linear_actor, args=(url, "alice", pid, Probe(point, child_barrier), child_events)
    )
    process.start()
    child_events.close()
    child_barrier.close()
    try:
        reached = wait_event(barrier)
        revision = service.append_message("alice", conv, "改为退货", "revision")
        barrier.send("release")
        result = wait_event(events)
        process.join(5)
        assert process.exitcode == 0
        state = snapshot(service.sessions)
        if case_id == "F06":
            assert not result["ok"] and result["error"] == "PREVIEW_INVALIDATED"
            unique_exchange(state, 0)
        else:
            assert (
                result["ok"] and service.get_operation("alice", preview_id=pid) == result["receipt"]
            )
            unique_exchange(state)
        return dict(
            triggered=True,
            evidence=[reached, {"new_revision": revision["revision"]}, result],
            state=state,
        )
    finally:
        if process.is_alive():
            process.kill()
            process.join(3)
        events.close()
        barrier.close()


def _sse_server(url, sock, events):
    import uvicorn

    from aftercare.api.app import create_app

    class ReadyServer(uvicorn.Server):
        async def startup(self, sockets=None):
            await super().startup(sockets=sockets)
            events.send(
                {
                    "event": "server_ready",
                    "pid": os.getpid(),
                    "started_at": time.time(),
                    "process_started_at": process_birth(os.getpid()),
                }
            )

    server = ReadyServer(
        uvicorn.Config(
            create_app(Settings(_env_file=None, database_url=url, app_env="test")),
            log_level="error",
            access_log=False,
        )
    )
    try:
        server.run(sockets=[sock])
    finally:
        events.close()


def sse_case(service):
    import socket

    import httpx

    conv, pid, _ = prepare(service)
    receipt = service.commit("alice", pid)
    url = service.sessions.kw["bind"].url.render_as_string(hide_password=False)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = sock.getsockname()[1]
    events, child_events = CTX.Pipe()
    process = CTX.Process(target=_sse_server, args=(url, sock, child_events))
    process.start()
    child_events.close()
    sock.close()
    try:
        evidence = [wait_event(events)]
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=10
        ) as client:
            who = client.post("/api/demo-sessions", json={"customer_id": "alice"}).json()
            client.headers["X-CSRF-Token"] = who["csrf_token"]
            before = snapshot(service.sessions)
            # Consume one event from a live, non-once response, then actually close TCP.
            with client.stream("GET", f"/api/conversations/{conv}/events") as stream:
                assert stream.status_code == 200
                cursor = next(
                    int(line[4:]) for line in stream.iter_lines() if line.startswith("id: ")
                )
            evidence.append({"live_connection_closed_at_event_id": cursor})
            endpoint = f"/api/conversations/{conv}/events?once=true"
            replay = client.get(endpoint, headers={"Last-Event-ID": str(cursor)}).text
            duplicated = client.get(endpoint, headers={"Last-Event-ID": str(cursor)}).text
            assert replay == duplicated
            ids = [int(line[4:]) for line in replay.splitlines() if line.startswith("id: ")]
            assert ids and min(ids) > cursor
            seen = {cursor, *ids}
            assert len(seen) == 1 + len(ids)
            state = snapshot(service.sessions)
            assert state["counts"] == before["counts"]
            assert state["receipts"] == [receipt]
            evidence.append(
                {
                    "resumed_ids": ids,
                    "client_unique_count": len(seen),
                    "duplicate_cursor_replayed": True,
                    "agent_and_effect_counts_unchanged": True,
                }
            )
        return dict(triggered=True, evidence=evidence, state=state)
    finally:
        if process.is_alive():
            process.terminate()
            process.join(5)
            if process.is_alive():
                process.kill()
                process.join(3)
        events.close()
