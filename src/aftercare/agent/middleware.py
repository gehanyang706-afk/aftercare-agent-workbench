import json

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from aftercare.agent.context import assemble_messages, case_model_context
from aftercare.agent.instructions import BUSINESS_INSTRUCTIONS
from aftercare.agent.tools import ALLOWED


class BusinessBoundary(AgentMiddleware):
    def __init__(self, service, principal, conversation, profile="full"):
        self.service, self.principal, self.conversation = service, principal, conversation
        self.profile = profile
        self.invalid_attempts = 0
        self.tool_attempts = 0
        self.read_retries = 0

    def wrap_model_call(self, request, handler):
        if self.invalid_attempts >= 2:
            return AIMessage(content="工具参数连续校验失败，已停止自动处理，请补充信息或转人工。")
        tools = [t for t in request.tools if getattr(t, "name", None) in ALLOWED]
        snapshot = self.service.snapshot(self.principal, self.conversation)
        humans = [m for m in request.messages if isinstance(m, HumanMessage)]
        users = [m for m in snapshot["messages"] if m["role"] == "user"]
        if humans and users and humans[-1].id != users[-1]["id"]:
            return AIMessage(content="旧方案已废弃，正在处理新诉求。")
        messages = request.messages
        starts = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
        if self.profile == "full" and len(starts) > 4:
            messages = messages[starts[-4] :]
        if self.profile == "full":
            messages = assemble_messages(messages)
        text = (
            BUSINESS_INSTRUCTIONS
            + "有效状态："
            + json.dumps(
                {
                    "case": case_model_context(snapshot)
                    if self.profile in {"full", "harness-evidence-v1"}
                    else {},
                    "intent_revision": snapshot["revision"],
                    "current_time": self.service.clock().isoformat(),
                    "current_user_message_id": users[-1]["id"] if users else None,
                },
                ensure_ascii=False,
            )
        )
        if self.profile == "harness-evidence-v1":
            from aftercare.agent.context import shared_evidence_context

            messages, context = shared_evidence_context(
                messages,
                text,
                [{"name": t.name, "parameters": t.args_schema.model_json_schema()} for t in tools],
            )
            with self.service.sessions.begin() as session:
                self.service._conversation(session, self.principal, self.conversation)
                self.service.event(
                    session,
                    self.conversation,
                    "context_prepared",
                    {
                        "policy_id": context.policy_id,
                        "estimated_size": context.estimated_size,
                        "selection_manifest": context.selection_manifest,
                    },
                )
        prepared = request.override(
            tools=tools, messages=messages, system_message=SystemMessage(content=text)
        )
        from aftercare.services.process_audit import audit_commit

        history = []
        for attempt in range(3):
            result = handler(prepared)
            replies = result.result if hasattr(result, "result") else [result]
            invalid = False
            from aftercare.services.intent_guard import user_evidence

            # Product owns evidence; evaluator diagnostics consume only observations.
            from aftercare.services.quantity_audit import quantity_claims

            evidence = user_evidence(users)
            for reply in replies:
                content = str(getattr(reply, "content", ""))
                if content:
                    with self.service.sessions.begin() as session:
                        self.service._conversation(session, self.principal, self.conversation)
                        self.service.event(
                            session, self.conversation, "model_text_proposal", {"text": content}
                        )
                        for claim in quantity_claims(content, evidence):
                            self.service.event(
                                session, self.conversation, "unconfirmed_quantity_claim", claim
                            )
                for call in getattr(reply, "tool_calls", []):
                    from aftercare.services.quantity_audit import quantity_proposal

                    proposal = quantity_proposal(call["name"], call["args"], evidence)
                    if proposal is not None:
                        with self.service.sessions.begin() as session:
                            self.service._conversation(session, self.principal, self.conversation)
                            self.service.event(
                                session, self.conversation, "quantity_tool_proposal", proposal
                            )
                    if call["name"] == "commit_action":
                        audit = audit_commit(
                            self.service,
                            self.principal,
                            self.conversation,
                            call["args"],
                            "proposal",
                        )
                        invalid |= audit["classification"] in {
                            "stale_or_unknown_preview",
                            "invalid_arguments",
                            "missing_trusted_confirmation",
                        }
            if not invalid:
                if hasattr(result, "result"):
                    result.result = history + replies
                return result
            # Never expose a stale proposal as a normal confirmation interrupt. Feed back
            # paired errors before the next (budgeted) model call; preserve its raw proposal.
            history.extend(replies)
            for reply in replies:
                for call in getattr(reply, "tool_calls", []):
                    history.append(
                        ToolMessage(
                            content=json.dumps(
                                {
                                    "ok": False,
                                    "data": None,
                                    "error_code": "PREVIEW_REVALIDATION_REQUIRED",
                                    "retryable": False,
                                    "user_message": (
                                        "该批次含失效提交提议，整批未执行。请核对诉求并重新预览。"
                                    ),
                                },
                                ensure_ascii=False,
                            ),
                            name=call["name"],
                            tool_call_id=call["id"],
                            status="error",
                        )
                    )
            if attempt == 2:
                from langchain.agents.middleware.types import ModelResponse

                return ModelResponse(
                    result=history + [AIMessage(content="预览已失效，未提交；请重新说明诉求。")]
                )
            prepared = prepared.override(messages=list(messages) + history)
        raise AssertionError("unreachable")

    def wrap_tool_call(self, request, handler):
        name = request.tool_call["name"]
        self.tool_attempts += 1
        if self.tool_attempts > 24:
            raise RuntimeError("TOOL_CALL_LIMIT")
        if name not in ALLOWED:
            with self.service.sessions.begin() as s:
                self.service._conversation(s, self.principal, self.conversation)
                self.service.event(s, self.conversation, "forbidden_tool_attempt", {"tool": name})
            return ToolMessage(
                content=json.dumps(
                    {
                        "ok": False,
                        "data": None,
                        "error_code": "TOOL_FORBIDDEN",
                        "retryable": False,
                        "user_message": "此工具不可用",
                        "trace_id": request.tool_call["id"],
                    }
                ),
                name=name,
                tool_call_id=request.tool_call["id"],
                status="error",
            )
        try:
            request.tool.args_schema.model_validate(request.tool_call["args"])
        except Exception:
            self.invalid_attempts += 1
            with self.service.sessions.begin() as session:
                self.service._conversation(session, self.principal, self.conversation)
                self.service.event(
                    session, self.conversation, "invalid_tool_attempt", {"tool": name}
                )
            return ToolMessage(
                content=json.dumps(
                    {
                        "ok": False,
                        "data": None,
                        "error_code": "INVALID_TOOL_ARGUMENTS",
                        "retryable": False,
                        "user_message": "工具参数不符合约定",
                        "trace_id": request.tool_call["id"],
                    }
                ),
                name=name,
                tool_call_id=request.tool_call["id"],
                status="error",
            )
        try:
            result = handler(request)
            reads = {
                "list_orders",
                "get_order",
                "get_inventory",
                "search_policies",
                "get_operation",
            }
            while name in reads and self.profile == "full":
                try:
                    payload = json.loads(str(result.content))
                except (ValueError, AttributeError):
                    break
                if not payload.get("retryable"):
                    break
                if self.read_retries >= 2:
                    payload["retryable"] = False
                    return ToolMessage(
                        content=json.dumps(payload),
                        name=name,
                        tool_call_id=request.tool_call["id"],
                        status="error",
                    )
                import time

                self.read_retries += 1
                time.sleep(0.05 * self.read_retries)
                result = handler(request)
            return result
        except Exception as e:
            # Parameter validation may occur before our function. Preserve call/result pairing.
            from pydantic import ValidationError

            if not isinstance(e, ValidationError):
                raise
            return ToolMessage(
                content=json.dumps(
                    {
                        "ok": False,
                        "data": None,
                        "error_code": "INVALID_TOOL_ARGUMENTS",
                        "retryable": False,
                        "user_message": "工具参数不符合约定",
                        "trace_id": request.tool_call["id"],
                    }
                ),
                name=name,
                tool_call_id=request.tool_call["id"],
                status="error",
            )
