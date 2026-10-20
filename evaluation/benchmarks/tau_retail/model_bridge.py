"""Scoped official completion-boundary bridge. Never patches a product provider.

All original generate import aliases still call llm_utils.generate, so a single physical
completion boundary covers Agent, user, NL assertions and reviews. Unknown callers are denied.
"""

import inspect
import time
from contextlib import contextmanager

from aftercare.harness.contracts import canonical


def role_at_boundary():
    for frame in inspect.stack():
        module = frame.frame.f_globals.get("__name__", "")
        if module == "tau2.agent.llm_agent" or module.endswith("tau_retail.adapter"):
            return "agent"
        if module == "tau2.user.user_simulator":
            return "user"
        if module.startswith("tau2.evaluator."):
            return "judge"
    raise ValueError("UNRECOGNIZED_MODEL_CALLER")


class CompletionBridge:
    def __init__(self, ledger, run_id, episode_id, roles, transport, trace, deadline):
        self.ledger, self.run, self.episode = ledger, run_id, episode_id
        self.roles, self.transport, self.trace, self.deadline = roles, transport, trace, deadline
        self.sequence = 0

    def __call__(self, **request):
        from litellm import ModelResponse

        role = role_at_boundary()
        cfg = self.roles.get(role, {})
        if not cfg.get("enabled"):
            raise ValueError("ROLE_NOT_APPROVED")
        if request["model"] != cfg["exact_model"] or request.get("num_retries", 0) != 0:
            raise ValueError("MODEL_OR_RETRY_SCOPE_MISMATCH")
        if time.time() >= self.deadline:
            raise TimeoutError("HARD_DEADLINE")
        allowed = {
            "model",
            "messages",
            "tools",
            "tool_choice",
            "temperature",
            "max_tokens",
            "num_retries",
            "extra_body",
            "timeout",
        }
        if set(request) - allowed:
            raise ValueError("UNSUPPORTED_PARAMETERS:" + str(sorted(set(request) - allowed)))
        if request.get("max_tokens") != cfg["output_cap"]:
            raise ValueError("OUTPUT_CAP_CHANGED")
        payload = {
            k: v for k, v in request.items() if k not in {"num_retries", "timeout", "extra_body"}
        }
        payload.update(request.get("extra_body") or {})
        self.sequence += 1
        # UTF-8 bytes + explicit framing margin is a conservative upper bound, not measured usage.
        input_bound = len(canonical(payload).encode()) + 2048
        call_id = self.ledger.reserve(
            self.run,
            self.episode,
            role,
            f"{self.episode}:{self.sequence}",
            input_bound,
            cfg["output_cap"],
        )
        self.trace.emit(
            "model.reserve",
            {"call_id": call_id, "input_bound": input_bound, "output_cap": cfg["output_cap"]},
            role,
        )
        self.trace.emit("model.sent", {"call_id": call_id, "payload": payload}, role)
        started = time.monotonic()
        try:
            raw = self.transport(payload, min(cfg["request_seconds"], self.deadline - time.time()))
        except BaseException:
            self.ledger.settle(call_id, None)
            self.trace.emit("model.unknown", {"call_id": call_id}, role)
            raise
        usage = raw.get("usage") or {}
        valid = all(
            type(usage.get(k)) is int and usage[k] >= 0
            for k in ("prompt_tokens", "completion_tokens", "total_tokens")
        )
        valid = valid and usage.get("total_tokens") == usage.get("prompt_tokens", 0) + usage.get(
            "completion_tokens", 0
        )
        settled = self.ledger.settle(
            call_id,
            usage["total_tokens"] if valid else None,
            {
                "usage_details": usage,
                "cost_cny": None,
                "model_wait_seconds": time.monotonic() - started,
            },
        )
        if not valid or settled is False:
            self.trace.emit("model.unknown", {"call_id": call_id, "usage": usage}, role)
            raise ValueError("USAGE_UNKNOWN")
        self.trace.emit("model.settled", {"call_id": call_id, "usage": usage}, role)
        # Usage is settled BEFORE validating choices, JSON arguments or protocol.
        if raw.get("model") != cfg["exact_model"]:
            raise ValueError("RESPONSE_MODEL_MISMATCH")
        response = ModelResponse(**raw)
        if not response.choices:
            raise ValueError("INVALID_MODEL_PROTOCOL")
        message = response.choices[0].message
        if message.tool_calls and message.content:
            raise ValueError("MIXED_TEXT_TOOL_PROTOCOL")
        for call in message.tool_calls or []:
            self.trace.emit("tool.proposed", call.model_dump(), role, tool_call_id=call.id)
        return response


@contextmanager
def official_bridge(completion):
    import litellm
    from tau2.utils import llm_utils

    saved, saved_cost = llm_utils.completion, llm_utils.get_response_cost
    prior = (
        litellm.telemetry,
        litellm.cache,
        litellm.success_callback,
        litellm.failure_callback,
        litellm.drop_params,
    )
    litellm.telemetry, litellm.cache = False, None
    litellm.success_callback, litellm.failure_callback = [], []
    litellm.drop_params = False
    llm_utils.completion = completion
    llm_utils.get_response_cost = lambda response: None  # Unknown price != zero cost.
    try:
        yield
    finally:
        llm_utils.completion, llm_utils.get_response_cost = saved, saved_cost
        (
            litellm.telemetry,
            litellm.cache,
            litellm.success_callback,
            litellm.failure_callback,
            litellm.drop_params,
        ) = prior
