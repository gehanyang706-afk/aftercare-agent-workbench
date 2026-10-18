"""Postgres queue + session advisory lock + lease + supervised child execution."""

import time
from datetime import timedelta

from sqlalchemy import or_, select, text

from aftercare.agent.runtime import run_turn
from aftercare.config import Settings
from aftercare.domain.contracts import BusinessError, utc_now
from aftercare.llm.budget import BudgetLedger
from aftercare.llm.supervisor import bounded
from aftercare.repositories.database import session_factory
from aftercare.repositories.models import Conversation, Job, Message
from aftercare.services.business import BusinessService, new_id


def execute_job(database_url, principal, conversation, message_id, kind, job_id, owner):
    from aftercare.offline import install_offline_guard

    install_offline_guard()
    settings = Settings(_env_file=None, database_url=database_url)
    sessions = session_factory(settings)

    def guard(s, conv):
        job = s.scalar(select(Job).where(Job.id == job_id).with_for_update(read=True))
        if (
            job is None
            or job.lease_owner != owner
            or job.status != "RUNNING"
            or job.cancel_requested
            or job.lease_expires_at < utc_now()
        ):
            raise BusinessError("WORKER_LEASE_LOST")

    service = BusinessService(sessions)
    service.run_guard = guard
    with sessions() as s:
        job_data = s.get(Job, job_id).result
        fault = job_data.get("fault")
        confirmation = job_data.get("confirmation")
    if fault in ["lost_response", "before_commit"]:
        service.commit_fault = fault
    if fault == "slow":
        BudgetLedger(sessions).reserve(
            "scripted", "aftercare:scripted", "offline", conversation, job_id, 1000, 512
        )
        time.sleep(600)
    try:
        result = run_turn(
            settings,
            service,
            principal,
            conversation,
            message_id,
            resume=kind != "message",
            run_id=job_id,
            decision="reject" if kind == "reject" else "approve",
            confirmation=confirmation,
        )
        messages = result.get("messages", [])
        last = messages[-1] if messages else None
        return {
            "text": str(last.content) if last and last.type == "ai" and not last.tool_calls else "",
            "interrupted": bool(result.get("__interrupt__")),
            "task_state": result.get("task_state", "WAITING_USER"),
            "graph_state": result.get("graph_state", "ENDED"),
            "notice_saved": result.get("notice_saved", False),
            "receipt": result.get("receipt"),
            "error_code": result.get("execution_stop")
            or (result.get("error") or {}).get("error_code"),
            "execution_stop": result.get("execution_stop"),
        }
    finally:
        sessions.kw["bind"].dispose()


class LeaseObserver:
    def __init__(self, sessions, job_id, owner):
        self.sessions, self.job_id, self.owner = sessions, job_id, owner
        self.next_check = 0
        self.cancelled = False

    def is_set(self):
        if time.monotonic() < self.next_check:
            return self.cancelled
        self.next_check = time.monotonic() + 0.3
        with self.sessions.begin() as s:
            job = s.get(Job, self.job_id, with_for_update=True)
            self.cancelled = job.cancel_requested or job.lease_owner != self.owner
            if not self.cancelled:
                job.lease_expires_at = utc_now() + timedelta(seconds=10)
        return self.cancelled


def run_once(settings, seconds=180):
    sessions = session_factory(settings)
    engine = sessions.kw["bind"]
    owner = new_id("worker")
    lease_connection = engine.connect()
    claimed = None
    try:
        with sessions.begin() as s:
            jobs = list(
                s.scalars(
                    select(Job)
                    .where(
                        or_(
                            Job.status == "PENDING",
                            (Job.status == "RUNNING") & (Job.lease_expires_at < utc_now()),
                        )
                    )
                    .order_by(Job.created_at, Job.revision, Job.id)
                    .with_for_update(skip_locked=True)
                    .limit(10)
                )
            )
            for job in jobs:
                acquired = lease_connection.scalar(
                    text("SELECT pg_try_advisory_lock(hashtextextended(:id,1))"),
                    {"id": job.conversation_id},
                )
                lease_connection.commit()
                if not acquired:
                    continue
                conv = s.get(Conversation, job.conversation_id)
                job.status = "RUNNING"
                job.lease_owner = owner
                job.lease_expires_at = utc_now() + timedelta(seconds=10)
                job.attempt += 1
                claimed = {
                    "id": job.id,
                    "conversation": conv.id,
                    "principal": conv.customer_id,
                    "message": job.message_id,
                    "kind": job.kind,
                    "revision": job.revision,
                }
                break
        if not claimed:
            return False
        service = BusinessService(sessions)
        status = "COMPLETED"
        result = {}
        try:
            result = bounded(
                execute_job,
                (
                    settings.database_url.get_secret_value(),
                    claimed["principal"],
                    claimed["conversation"],
                    claimed["message"],
                    claimed["kind"],
                    claimed["id"],
                    owner,
                ),
                seconds=seconds,
                cancel=LeaseObserver(sessions, claimed["id"], owner),
            )
        except TimeoutError as e:
            status = "CANCELLED" if str(e) == "TASK_CANCELLED" else "FAILED"
            result = {
                "error_code": str(e),
                "text": "处理已停止；请查看实际回执，已提交的申请不会被自动撤销。",
            }
            BudgetLedger(sessions).mark_unresolved_unknown(claimed["conversation"], claimed["id"])
        except Exception:
            status = "FAILED"
            result = {
                "error_code": "WORKER_FAILED",
                "text": "处理异常，请查看实际操作回执后重试或转人工。",
            }
            BudgetLedger(sessions).mark_unresolved_unknown(claimed["conversation"], claimed["id"])
        if status == "COMPLETED":
            task_state = result.get("task_state", "FAILED")
            status = (
                "COMPLETED"
                if task_state in {"COMPLETED", "REJECTED", "HANDOFF_PENDING"}
                else task_state
            )
        with sessions.begin() as s:
            conv = s.scalar(
                select(Conversation)
                .where(Conversation.id == claimed["conversation"])
                .with_for_update()
            )
            job = s.get(Job, claimed["id"], with_for_update=True)
            if job.lease_owner != owner:
                return True
            job.status = status
            job.result = result
            job.lease_expires_at = None
            if conv.revision == claimed["revision"]:
                if result.get("text") and not result.get("notice_saved"):
                    existing = s.scalar(
                        select(Message.id).where(
                            Message.conversation_id == conv.id,
                            Message.client_message_id == "assistant:" + job.id,
                        )
                    )
                    if not existing:
                        s.add(
                            Message(
                                id=new_id("msg"),
                                conversation_id=conv.id,
                                client_message_id="assistant:" + job.id,
                                role="assistant",
                                text=result["text"],
                                revision=conv.revision,
                                created_at=utc_now(),
                            )
                        )
                if conv.status not in {
                    "WAITING_CONFIRMATION",
                    "WAITING_SUBMISSION",
                    "COMPLETED",
                    "HANDOFF_PENDING",
                }:
                    conv.status = (
                        "WAITING_USER" if status in {"COMPLETED", "WAITING_USER"} else status
                    )
            service.event(
                s, conv.id, "job_finished", {"job_id": job.id, "status": status, "result": result}
            )
        return True
    finally:
        if claimed:
            lease_connection.execute(
                text("SELECT pg_advisory_unlock(hashtextextended(:id,1))"),
                {"id": claimed["conversation"]},
            )
            lease_connection.commit()
        lease_connection.close()
        engine.dispose()


def work(settings, once=False):
    while True:
        active = run_once(settings)
        if once:
            return
        if not active:
            time.sleep(0.3)
