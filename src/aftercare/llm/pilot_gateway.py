"""One approved pilot, same Bailian adapter/transport and BudgetLedger as smoke."""

import hashlib
import json
import time
from pathlib import Path

from aftercare.domain.rules import require
from aftercare.llm.budget import BudgetLedger
from aftercare.llm.provider import BailianAdapter
from aftercare.llm.smoke import MODEL, parse_usage, send_once, write_json
from aftercare.llm.supervisor import bounded
from aftercare.repositories.models import ModelCall

BATCH = "development-pilot"
PLAN_HASH = "9eb8329777e719103f86c188bea0d99d84ec4a9250f2a31575e2a76fd810d894"


class PilotGateway:
    def __init__(
        self,
        settings,
        ledger_sessions,
        ledger_conversation,
        service,
        principal,
        conversation,
        run_id,
        deadline,
        trace_directory,
        permit,
    ):
        if permit.get("batch_id") == BATCH:
            require(permit.get("plan_sha256") == PLAN_HASH, "PILOT_APPROVAL_REQUIRED")
            self.batch, self.plan_hash = BATCH, PLAN_HASH
            self.batch_cap, self.task_cap, self.request_cap = 96000, 24000, 64
        else:
            from aftercare.llm.regression_scope import read_scope

            scope = read_scope(permit)
            self.batch, self.plan_hash = scope["batch_id"], scope["plan_sha256"]
            self.batch_cap = scope["total_token_hard_cap"]
            from aftercare.llm.regression_scope import bound_task_token_cap

            self.task_cap = bound_task_token_cap(scope, ledger_sessions, ledger_conversation)
            self.request_cap = scope["max_http_requests_including_retries"]
        require(settings.allow_real_model_calls, "EXPLICIT_REAL_CALL_FLAG_REQUIRED")
        self.settings = settings
        self.ledger = BudgetLedger(ledger_sessions)
        self.ledger_conversation = ledger_conversation
        self.service, self.principal, self.conversation = service, principal, conversation
        self.run_id, self.deadline = run_id, deadline
        self.trace_directory = Path(trace_directory)
        self.trace_directory.mkdir(parents=True, exist_ok=True)
        self.adapter = BailianAdapter(
            settings.dashscope_base_url.get_secret_value(), settings.dashscope_api_key
        )

    def security_attempt(self, tool, args):
        if tool == "commit_action":
            from aftercare.services.process_audit import audit_commit

            audit_commit(self.service, self.principal, self.conversation, args, "proposal")
        with self.service.sessions.begin() as session:
            self.service._conversation(session, self.principal, self.conversation)
            self.service.event(
                session,
                self.conversation,
                "forbidden_tool_attempt",
                {"tool": tool, "argument_keys": sorted(args)},
            )
        require(False, "SECURITY_UNAUTHORIZED_TOOL_ATTEMPT")

    def invoke(self, messages, tools):
        remaining = self.deadline - time.time()
        require(remaining > 0, "TASK_DEADLINE_EXCEEDED")
        request = self.adapter.prepare(MODEL, messages, tools, max_tokens=512)
        payload = json.loads(request.content)
        call_id = self.ledger.reserve(
            "bailian-beijing-compatible",
            MODEL,
            self.batch,
            self.ledger_conversation,
            self.run_id,
            len(request.content) + 1024,
            512,
            self.batch_cap,
            conversation_cap=self.task_cap,
            batch_request_cap=self.request_cap,
        )
        write_json(
            self.trace_directory / f"{call_id}.request.json",
            {
                "plan_sha256": self.plan_hash,
                "call_id": call_id,
                "request": payload,
                "business_conversation": self.conversation,
                "ledger_conversation": self.ledger_conversation,
            },
        )
        started = time.monotonic()
        try:
            result = bounded(
                send_once,
                (
                    self.settings.dashscope_base_url.get_secret_value().rstrip("/"),
                    self.settings.dashscope_api_key.get_secret_value(),
                    payload,
                ),
                seconds=min(60, remaining),
            )
            write_json(self.trace_directory / f"{call_id}.response.json", result)
            require(
                result.get("http_status") == 200,
                "PROVIDER_HTTP_" + str(result.get("http_status", "TRANSPORT_ERROR")),
            )
            usage = parse_usage(result.get("usage"))
            self.ledger.settle(call_id, usage[2], request_id=result.get("request_id"))
            with self.ledger.sessions.begin() as session:
                call = session.get(ModelCall, call_id)
                call.details = {
                    **call.details,
                    "input_tokens": usage[0],
                    "output_tokens": usage[1],
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "wire_sha256": hashlib.sha256(request.content).hexdigest(),
                    "business_conversation": self.conversation,
                    "plan_sha256": self.plan_hash,
                }
            require(result.get("data", {}).get("model") == MODEL, "PROVIDER_PROTOCOL_MODEL")
            require(usage[1] <= 512, "PROVIDER_PROTOCOL_OUTPUT_CAP")
            return result, usage
        except BaseException:
            with self.ledger.sessions() as session:
                settled = session.get(ModelCall, call_id).status == "SETTLED"
            if not settled:
                self.ledger.settle(call_id, None)
            raise
