"""Persistent multi-role reservations share the original project's total Budget row.

Lock order: project -> shared model -> run -> episode -> sorted budget dimensions -> call.
No network client is created here. Reserved attempts survive a process crash and cannot replay.
"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from aftercare.domain.contracts import utc_now
from aftercare.domain.rules import require
from aftercare.llm.experiment_scope import ALIASES, model_identity
from aftercare.repositories.models import (
    ActorBudget,
    Budget,
    Conversation,
    Customer,
    ExperimentCall,
    ExperimentEpisode,
    ExperimentRun,
    ModelCall,
    SharedModelQuota,
)
from aftercare.services.business import new_id


class ExperimentLedger:
    def __init__(self, sessions):
        self.sessions = sessions

    def create_run(self, run_id, plan, account):
        """Called only after authorization by the runner; never refresh a quota on restart."""
        with self.sessions.begin() as s:
            s.execute(
                insert(Budget)
                .values(id="project", cap=2000000, settled=0, reserved=0, paused=False)
                .on_conflict_do_nothing(index_elements=["id"])
            )
            s.get(Budget, "project", with_for_update=True)
            existing = s.get(ExperimentRun, run_id)
            if existing:
                require(existing.plan_hash == plan["plan_sha256"], "RUN_PLAN_CHANGED")
                raise ValueError("RUN_RESTART_READ_ONLY")
            now = utc_now()
            s.add(
                ExperimentRun(
                    id=run_id,
                    plan_hash=plan["plan_sha256"],
                    config=plan,
                    deadline=now + timedelta(seconds=plan["wall_clock_seconds"]),
                )
            )
            s.flush()
            for key, confirmation in sorted(account["models"].items()):
                all_calls = list(s.scalars(select(ModelCall)))
                watermark = [c.id for c in all_calls]
                prior = s.get(SharedModelQuota, key, with_for_update=True)
                exact = key.split(":", 2)[2]
                legacy_paused = any(
                    c.exact_model == exact
                    and c.provider.lower() in ALIASES
                    and (c.usage is None or s.get(Budget, c.budget_id).paused)
                    for c in all_calls
                )
                if prior:
                    prior.paused = prior.paused or legacy_paused
                    old = set(prior.watermark["call_ids"])
                    used = sum(
                        c.usage if c.usage is not None else c.reserved
                        for c in all_calls
                        if c.exact_model == exact and c.id not in old
                    )
                    # Current confirmation can lower a quota, never revive a paused model
                    # or transfer a batch cap. Historical consumption is not subtracted twice.
                    prior.confirmed_remaining = min(
                        confirmation["remaining"], max(0, prior.confirmed_remaining - used)
                    )
                    prior.watermark = {"call_ids": watermark}
                    prior.confirmation = account
                else:
                    s.add(
                        SharedModelQuota(
                            id=key,
                            confirmed_remaining=confirmation["remaining"],
                            watermark={"call_ids": watermark},
                            confirmation=account,
                            paused=legacy_paused,
                        )
                    )
            self._dimension(
                s,
                run_id + ":batch",
                run_id,
                None,
                "all",
                plan["total_token_cap"],
                plan["request_cap"],
            )
            for role, cfg in plan["roles"].items():
                if cfg.get("enabled"):
                    self._dimension(
                        s,
                        run_id + ":" + role,
                        run_id,
                        None,
                        role,
                        cfg["batch_token_cap"],
                        cfg["batch_request_cap"],
                    )

    def create_episode(self, run_id, episode_id, config):
        with self.sessions.begin() as s:
            run = s.get(ExperimentRun, run_id, with_for_update=True)
            require(run is not None and run.status == "READY", "RUN_NOT_READY")
            require(s.get(ExperimentEpisode, episode_id) is None, "EPISODE_REPLAY_FORBIDDEN")
            customer = "benchmark-ledger-only"
            s.execute(
                insert(Customer)
                .values(id=customer, name="Isolated benchmark accounting")
                .on_conflict_do_nothing(index_elements=["id"])
            )
            conversation = "benchmark:" + episode_id
            s.add(
                Conversation(
                    id=conversation,
                    customer_id=customer,
                    revision=0,
                    status="BENCHMARK_LEDGER_ONLY",
                    case={},
                )
            )
            s.flush()
            s.add(
                ExperimentEpisode(
                    id=episode_id,
                    run_id=run_id,
                    conversation_id=conversation,
                    config=config,
                    deadline=min(
                        run.deadline, utc_now() + timedelta(seconds=run.config["episode_seconds"])
                    ),
                )
            )
            s.flush()
            self._dimension(
                s,
                episode_id + ":all",
                run_id,
                episode_id,
                "all",
                run.config["episode_token_cap"],
                run.config["episode_request_cap"],
            )
            for role, cfg in run.config["roles"].items():
                if cfg.get("enabled"):
                    self._dimension(
                        s,
                        episode_id + ":" + role,
                        run_id,
                        episode_id,
                        role,
                        cfg["episode_token_cap"],
                        cfg["request_cap"],
                    )

    @staticmethod
    def _dimension(s, key, run_id, episode, role, cap, requests):
        s.add(
            ActorBudget(
                id=key,
                run_id=run_id,
                episode_id=episode,
                role=role,
                cap=cap,
                request_cap=requests,
                settled=0,
                reserved=0,
                requests=0,
            )
        )

    def reserve(self, run_id, episode_id, role, attempt_id, input_bound, output_cap):
        require(input_bound >= 0 and output_cap > 0, "INVALID_RESERVATION")
        amount = input_bound + output_cap
        with self.sessions.begin() as s:
            s.execute(
                insert(Budget)
                .values(id="project", cap=2000000, settled=0, reserved=0, paused=False)
                .on_conflict_do_nothing(index_elements=["id"])
            )
            project = s.get(Budget, "project", with_for_update=True)
            run_data = s.get(ExperimentRun, run_id)
            require(run_data is not None, "RUN_NOT_FOUND")
            cfg = run_data.config["roles"].get(role, {})
            require(cfg.get("enabled") is True, "ROLE_NOT_APPROVED")
            episode_data = s.get(ExperimentEpisode, episode_id)
            require(episode_data is not None, "EPISODE_NOT_FOUND")
            require(
                not cfg.get("task_ids") or episode_data.config.get("task_id") in cfg["task_ids"],
                "ROLE_NOT_APPROVED_FOR_TASK",
            )
            key = model_identity(cfg["provider"], cfg["region"], cfg["exact_model"])
            quota = s.get(SharedModelQuota, key, with_for_update=True)
            require(quota is not None and not quota.paused, "SHARED_MODEL_PAUSED")
            # Legacy unresolved attempts pause this exact model even across provider aliases.
            prior = list(
                s.scalars(select(ModelCall).where(ModelCall.exact_model == cfg["exact_model"]))
            )
            require(
                not any(
                    c.usage is None
                    and c.provider.lower() in ALIASES
                    and (
                        c.status == "USAGE_UNKNOWN"
                        or c.details.get("request_deadline", 0) <= utc_now().timestamp()
                    )
                    for c in prior
                ),
                "UNRESOLVED_MODEL_USAGE",
            )
            watermark = set(quota.watermark["call_ids"])
            consumed = sum(
                c.usage if c.usage is not None else c.reserved
                for c in prior
                if c.id not in watermark
            )
            require(consumed + amount <= quota.confirmed_remaining, "SHARED_QUOTA_EXHAUSTED")
            run = s.get(ExperimentRun, run_id, with_for_update=True)
            episode = s.get(ExperimentEpisode, episode_id, with_for_update=True)
            require(episode is not None and episode.run_id == run_id, "EPISODE_NOT_FOUND")
            require(run.status == episode.status == "READY", "EXPERIMENT_STOPPED")
            require(utc_now() < min(run.deadline, episode.deadline), "EXPERIMENT_DEADLINE")
            require(output_cap == cfg["output_cap"], "OUTPUT_CAP_CHANGED")
            require(
                s.scalar(select(ExperimentCall).where(ExperimentCall.attempt_id == attempt_id))
                is None,
                "ATTEMPT_REPLAY_FORBIDDEN",
            )
            recent = list(
                s.scalars(
                    select(ModelCall)
                    .where(ModelCall.run_id == episode_id)
                    .order_by(ModelCall.created_at.desc())
                )
            )
            consecutive = 0
            for previous in recent:
                if previous.details.get("role") != role:
                    break
                consecutive += 1
            require(
                consecutive < run.config.get("consecutive_request_cap", 24),
                "CONSECUTIVE_REQUEST_LIMIT",
            )
            ids = sorted(
                [
                    run_id + ":batch",
                    run_id + ":" + role,
                    episode_id + ":all",
                    episode_id + ":" + role,
                ]
            )
            dimensions = [s.get(ActorBudget, k, with_for_update=True) for k in ids]
            require(
                project.settled + project.reserved + amount <= project.cap, "PROJECT_TOKEN_LIMIT"
            )
            require(not project.paused, "PROJECT_PAUSED")
            for row in dimensions:
                require(row.settled + row.reserved + amount <= row.cap, "ACTOR_TOKEN_LIMIT")
                require(row.requests < row.request_cap, "ACTOR_REQUEST_LIMIT")
            for row in [project, *dimensions]:
                row.reserved += amount
            for row in dimensions:
                row.requests += 1
            budget_id = "experiment:" + run_id
            s.execute(
                insert(Budget)
                .values(
                    id=budget_id,
                    cap=run.config["total_token_cap"],
                    settled=0,
                    reserved=0,
                    paused=False,
                )
                .on_conflict_do_nothing(index_elements=["id"])
            )
            budget = s.get(Budget, budget_id, with_for_update=True)
            budget.reserved += amount
            call_id = new_id("call")
            metadata = dict(
                experiment_id=run_id,
                batch_id=run_id,
                episode_id=episode_id,
                role=role,
                attempt_id=attempt_id,
                plan_hash=run.plan_hash,
                **episode.config,
            )
            s.add(
                ModelCall(
                    id=call_id,
                    budget_id=budget_id,
                    provider="dashscope",
                    exact_model=cfg["exact_model"],
                    batch_id=run_id,
                    conversation_id=episode.conversation_id,
                    run_id=episode_id,
                    reserved=amount,
                    usage=None,
                    status="RESERVED",
                    details={
                        "input_bound": input_bound,
                        "output_cap": output_cap,
                        **metadata,
                        "request_deadline": min(
                            run.deadline,
                            episode.deadline,
                            utc_now() + timedelta(seconds=cfg.get("request_seconds", 60)),
                        ).timestamp(),
                    },
                    created_at=utc_now(),
                )
            )
            s.flush()
            s.add(
                ExperimentCall(
                    call_id=call_id,
                    quota_id=key,
                    run_id=run_id,
                    episode_id=episode_id,
                    role=role,
                    attempt_id=attempt_id,
                    dimensions=ids,
                    metadata_=metadata,
                )
            )
            return call_id

    def settle(self, call_id, usage, details=None):
        with self.sessions.begin() as s:
            project = s.get(Budget, "project", with_for_update=True)
            mapping = s.get(ExperimentCall, call_id)
            require(mapping is not None, "EXPERIMENT_CALL_NOT_FOUND")
            quota = s.get(SharedModelQuota, mapping.quota_id, with_for_update=True)
            run = s.get(ExperimentRun, mapping.run_id, with_for_update=True)
            episode = s.get(ExperimentEpisode, mapping.episode_id, with_for_update=True)
            dimensions = [s.get(ActorBudget, k, with_for_update=True) for k in mapping.dimensions]
            call = s.get(ModelCall, call_id, with_for_update=True)
            if call.status == "SETTLED":
                return True
            require(
                call.status != "USAGE_UNKNOWN" or usage is None,
                "MANUAL_USAGE_RECONCILIATION_REQUIRED",
            )
            if usage is None or usage < 0 or usage > call.reserved:
                quota.paused = True
                run.status = episode.status = "PAUSED_UNKNOWN_USAGE"
                call.status = "USAGE_UNKNOWN"
                return False
            budget = s.get(Budget, call.budget_id, with_for_update=True)
            for row in [project, budget, *dimensions]:
                row.reserved -= call.reserved
                row.settled += usage
            call.usage, call.status = usage, "SETTLED"
            call.details = {**call.details, **(details or {})}
            return True
