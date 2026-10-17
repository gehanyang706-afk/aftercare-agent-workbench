"""All attempts reserve first. Unknown usage keeps reservations and pauses that model."""

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from aftercare.domain.contracts import utc_now
from aftercare.domain.rules import require
from aftercare.repositories.models import Budget, ModelCall
from aftercare.services.business import new_id


class BudgetLedger:
    def __init__(self, sessions):
        self.sessions = sessions

    def reserve(
        self, provider, model, batch, conversation, run, input_bound, output_cap, cap=200000
    ):
        require(input_bound >= 0 and output_cap > 0, "INVALID_RESERVATION")
        key = f"{provider}:{model}:{batch}"
        amount = input_bound + output_cap
        with self.sessions.begin() as s:
            for budget_id, limit in [("project", 2000000), (key, cap)]:
                s.execute(
                    insert(Budget)
                    .values(id=budget_id, cap=limit, settled=0, reserved=0, paused=False)
                    .on_conflict_do_nothing(index_elements=["id"])
                )
            project = s.scalar(select(Budget).where(Budget.id == "project").with_for_update())
            budget = s.scalar(select(Budget).where(Budget.id == key).with_for_update())
            require(not budget.paused, "MODEL_BUDGET_PAUSED")
            require(budget.cap == cap, "BUDGET_CAP_CHANGE_REQUIRES_APPROVAL")
            for row in [project, budget]:
                require(row.settled + row.reserved + amount <= row.cap, "BUDGET_EXHAUSTED")
            calls = s.scalar(
                select(func.count())
                .select_from(ModelCall)
                .where(ModelCall.conversation_id == conversation)
            )
            run_calls = s.scalar(
                select(func.count()).select_from(ModelCall).where(ModelCall.run_id == run)
            )
            require(calls < 16 and run_calls < 8, "MODEL_CALL_LIMIT")
            prior = s.scalar(
                select(func.coalesce(func.sum(ModelCall.usage + 0), 0)).where(
                    ModelCall.conversation_id == conversation
                )
            )
            require(prior + amount <= 100000, "CONVERSATION_TOKEN_LIMIT")
            for row in [project, budget]:
                row.reserved += amount
            call_id = new_id("call")
            s.add(
                ModelCall(
                    id=call_id,
                    budget_id=key,
                    provider=provider,
                    exact_model=model,
                    batch_id=batch,
                    conversation_id=conversation,
                    run_id=run,
                    reserved=amount,
                    status="RESERVED",
                    usage=None,
                    details={"input_bound": input_bound, "output_cap": output_cap},
                    created_at=utc_now(),
                )
            )
            return call_id

    def settle(self, call_id, usage, request_id=None):
        with self.sessions.begin() as s:
            call = s.get(ModelCall, call_id)
            require(call is not None, "CALL_NOT_FOUND")
            project = s.scalar(select(Budget).where(Budget.id == "project").with_for_update())
            budget = s.scalar(select(Budget).where(Budget.id == call.budget_id).with_for_update())
            s.refresh(call, with_for_update=True)
            if call.status == "SETTLED":
                return
            if usage is None:
                call.status = "USAGE_UNKNOWN"
                budget.paused = True
                return
            require(0 <= usage <= call.reserved, "USAGE_EXCEEDS_RESERVATION")
            for row in [project, budget]:
                row.reserved -= call.reserved
                row.settled += usage
            call.usage = usage
            call.status = "SETTLED"
            call.request_id = request_id

    def mark_unresolved_unknown(self, conversation, run=None):
        with self.sessions() as s:
            q = select(ModelCall.id).where(
                ModelCall.conversation_id == conversation, ModelCall.status == "RESERVED"
            )
            if run:
                q = q.where(ModelCall.run_id == run)
            ids = list(s.scalars(q))
        for call_id in ids:
            self.settle(call_id, None)
