"""Concrete request-shape dry run. Never constructs a live client or loads a real Key."""

import hashlib
import json

from pydantic import SecretStr

from aftercare.config import PROJECT_ROOT
from aftercare.llm.provider import BailianAdapter


def compatibility_plan():
    model = "qwen3.5-plus-2026-02-15"
    adapter = BailianAdapter(
        "https://dashscope.aliyuncs.com/compatible-mode/v1", SecretStr("DRY-RUN-NOT-A-KEY")
    )
    tool = {
        "type": "function",
        "function": {
            "name": "get_order",
            "description": "Read the current user's demo order",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
                "additionalProperties": False,
            },
        },
    }
    definitions = [
        ("plain-text", [{"role": "user", "content": "Reply with OK."}], None, False),
        (
            "tool-call",
            [{"role": "user", "content": "Use get_order to read demo order S1002."}],
            [tool],
            False,
        ),
        (
            "tool-result",
            [
                {"role": "user", "content": "Read order S1002"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "dry-call",
                            "type": "function",
                            "function": {"name": "get_order", "arguments": '{"order_id":"S1002"}'},
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "dry-call",
                    "content": '{"ok":true,"data":{"id":"S1002","status":"DELIVERED"}}',
                },
            ],
            [tool],
            False,
        ),
        ("stream-usage", [{"role": "user", "content": "Reply OK in one word."}], None, True),
        (
            "validated-json",
            [
                {
                    "role": "user",
                    "content": 'Return JSON with action="query" and order_id="S1002".',
                }
            ],
            None,
            False,
        ),
        (
            "tool-schema-check",
            [
                {
                    "role": "user",
                    "content": "Read S1002. Never invent identity fields or extra arguments.",
                }
            ],
            [tool],
            False,
        ),
    ]
    rows = []
    for name, messages, tools, stream in definitions:
        request = adapter.prepare(model, messages, tools, stream, max_tokens=128)
        payload = json.loads(request.content)
        bound = len(request.content) + 1024 + 128
        rows.append(
            {
                "scenario": name,
                "request": payload,
                "input_bound": len(request.content) + 1024,
                "output_cap": 128,
                "reserved_bound": bound,
            }
        )
    # Two retries are budgeted, never automatically made. Each remains <= largest request bound.
    maximum = max(r["reserved_bound"] for r in rows)
    reserved = sum(r["reserved_bound"] for r in rows) + maximum * 2
    if reserved > 20000:
        raise ValueError("SMOKE_PLAN_OVER_BUDGET")
    output = {
        "batch_id": "compatibility-smoke",
        "status": "DRAFT_REQUIRES_EXPLICIT_HUMAN_APPROVAL",
        "provider": "bailian-beijing-compatible",
        "exact_model": model,
        "enable_thinking": False,
        "planned_requests": 6,
        "retry_slots": 2,
        "max_http_requests_including_retries": 8,
        "total_token_hard_cap": 20000,
        "conservative_reservation": reserved,
        "per_request_hard_cap": maximum,
        "output_cap": 128,
        "concurrency": 1,
        "wall_clock_seconds": 600,
        "per_request_seconds": 60,
        "sdk_retries": 0,
        "stop_conditions": [
            "auth/model/region/quota failure",
            "any unknown usage or disconnect",
            "tool/usage/schema incompatibility",
            "request, token or time cap",
            "human cancellation",
        ],
        "forbidden": [
            "automatic model switch",
            "automatic batch expansion",
            "holdout access",
            "paid overage without separate authorization",
        ],
        "requests": rows,
        "real_api_calls": 0,
        "follow_up": (
            "Only this compatibility batch; development-pilot and formal comparison "
            "need separate plans and approval."
        ),
    }
    output["plan_sha256"] = hashlib.sha256(
        json.dumps(output, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    path = PROJECT_ROOT / "evaluation/manifests/compatibility-smoke.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    return output
