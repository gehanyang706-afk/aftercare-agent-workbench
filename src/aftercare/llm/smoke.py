"""Single approved compatibility batch. No general-purpose live Agent entrypoint."""

import hashlib
import ipaddress
import json
import socket
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select, text
from sqlalchemy.engine import make_url

from aftercare.config import PROJECT_ROOT
from aftercare.domain.rules import require
from aftercare.llm.budget import BudgetLedger
from aftercare.llm.supervisor import bounded
from aftercare.repositories.database import is_local_database, session_factory
from aftercare.repositories.models import ModelCall
from aftercare.services.business import BusinessService

APPROVED_HASH = "3392fe79d3877477b2d8acc2cfebbd58a46c6486b0b77279c632af967e8357f1"
MODEL = "qwen3.5-plus-2026-02-15"
BATCH = "compatibility-smoke"


def now():
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as output:
        json.dump(value, output, ensure_ascii=False, indent=2)
        output.write("\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def validate_authorization(settings, approval, account, plan):
    values = dict(plan)
    declared = values.pop("plan_sha256")
    digest = hashlib.sha256(
        json.dumps(values, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    require(digest == declared == APPROVED_HASH, "APPROVED_PLAN_HASH_MISMATCH")
    require(approval.get("plan_sha256") == digest, "APPROVAL_PLAN_MISMATCH")
    require(
        approval.get("source") == "Explicit user message in this chat", "HUMAN_APPROVAL_REQUIRED"
    )
    for key, value in {
        "batch_id": BATCH,
        "exact_model": MODEL,
        "max_http_requests_including_retries": 8,
        "total_token_cap": 20000,
        "concurrency": 1,
        "wall_clock_seconds": 600,
        "additional_paid_cost_cap_cny": 0,
    }.items():
        require(approval.get(key) == value, "AUTHORIZATION_LIMIT_MISMATCH")
    require(
        all(
            account.get(k) is True
            for k in (
                "beijing_key_confirmed",
                "free_tier_only_confirmed",
                "sufficient_quota_confirmed",
            )
        ),
        "ACCOUNT_PROTECTION_CONFIRMATION_REQUIRED",
    )
    require(account.get("plan_sha256") == digest, "ACCOUNT_CONFIRMATION_PLAN_MISMATCH")
    require(settings.allow_real_model_calls, "EXPLICIT_REAL_CALL_FLAG_REQUIRED")
    require(bool(settings.dashscope_api_key.get_secret_value().strip()), "KEY_MISSING")
    url = urlsplit(settings.dashscope_base_url.get_secret_value().strip())
    require(
        url.scheme == "https"
        and not url.username
        and not url.password
        and not url.query
        and not url.fragment
        and url.port in {None, 443},
        "HTTPS_ENDPOINT_REQUIRED",
    )
    require(
        url.hostname == "dashscope.aliyuncs.com"
        or bool(url.hostname and url.hostname.endswith(".cn-beijing.maas.aliyuncs.com")),
        "BEIJING_ENDPOINT_REQUIRED",
    )
    require(url.path.rstrip("/") == "/compatible-mode/v1", "COMPATIBLE_ENDPOINT_REQUIRED")
    require(
        is_local_database(make_url(settings.database_url.get_secret_value())),
        "LOCAL_LEDGER_REQUIRED",
    )
    require(plan["exact_model"] == MODEL and len(plan["requests"]) == 6, "BATCH_SHAPE_INVALID")
    return digest


def _network_guard(host):
    addresses = {r[4][0] for r in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}

    def audit(event, args):
        if event == "socket.getaddrinfo" and args[0] != host:
            raise PermissionError("SMOKE_HOST_NOT_ALLOWED")
        if event == "socket.connect":
            sock, address = args
            if sock.family in {socket.AF_INET, socket.AF_INET6}:
                if str(ipaddress.ip_address(address[0])) not in addresses or address[1] != 443:
                    raise PermissionError("SMOKE_DESTINATION_NOT_ALLOWED")
        if event == "socket.sendto":
            raise PermissionError("SMOKE_UDP_NOT_ALLOWED")

    sys.addaudithook(audit)


def send_once(endpoint, key, payload):
    """Executed in a killable child; exactly one POST, no redirects/proxy/SDK retries."""
    _network_guard(urlsplit(endpoint).hostname)
    try:
        transport = httpx.HTTPTransport(retries=0)
        with httpx.Client(
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(55, connect=10),
        ) as client:
            with client.stream(
                "POST",
                endpoint + "/chat/completions",
                json=payload,
                headers={"Authorization": "Bearer " + key},
            ) as response:
                request_id = response.headers.get("x-request-id") or response.headers.get(
                    "x-dashscope-request-id"
                )
                if response.status_code != 200:
                    # Do not log arbitrary error bodies or exception strings containing credentials.
                    return {
                        "http_status": response.status_code,
                        "request_id": request_id,
                        "usage": None,
                        "error": "HTTP_ERROR",
                    }
                size = 0
                if not payload.get("stream"):
                    chunks = []
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > 131072:
                            raise ValueError("RESPONSE_SIZE_LIMIT")
                        chunks.append(chunk)
                    data = json.loads(b"".join(chunks))
                    return {
                        "http_status": 200,
                        "request_id": request_id or data.get("id"),
                        "usage": data.get("usage"),
                        "data": data,
                    }
                events, done = [], False
                for line in response.iter_lines():
                    size += len(line.encode())
                    if size > 131072:
                        raise ValueError("RESPONSE_SIZE_LIMIT")
                    if not line.startswith("data:"):
                        continue
                    content = line[5:].strip()
                    if content == "[DONE]":
                        done = True
                        break
                    events.append(json.loads(content))
                usage = next((e["usage"] for e in reversed(events) if e.get("usage")), None)
                return {
                    "http_status": 200,
                    "request_id": request_id,
                    "usage": usage,
                    "events": events,
                    "stream_done": done,
                }
    except Exception as e:
        return {"usage": None, "error": type(e).__name__}


def parse_usage(usage):
    require(isinstance(usage, dict), "USAGE_UNKNOWN")
    values = [usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")]
    require(all(type(v) is int and v >= 0 for v in values), "USAGE_INVALID")
    incoming, outgoing, total = values
    require(incoming + outgoing == total, "USAGE_TOTAL_MISMATCH")
    return incoming, outgoing, total


def validate_response(scenario, result):
    require(result.get("http_status") == 200, "HTTP_ERROR")
    if "events" in result:
        require(result.get("stream_done"), "STREAM_INCOMPLETE")
        events = result["events"]
        content = "".join(
            c.get("delta", {}).get("content") or "" for e in events for c in e.get("choices", [])
        )
        models = {e.get("model") for e in events if e.get("model")}
        finishes = [
            c.get("finish_reason")
            for e in events
            for c in e.get("choices", [])
            if c.get("finish_reason")
        ]
        message = {"content": content}
    else:
        data = result.get("data", {})
        choices = data.get("choices", [])
        require(len(choices) == 1, "CHOICE_COUNT_INVALID")
        message = choices[0].get("message", {})
        models = {data.get("model")}
        finishes = [choices[0].get("finish_reason")]
    require(models == {MODEL}, "RETURNED_MODEL_MISMATCH")
    require(finishes and finishes[-1] in {"stop", "tool_calls"}, "FINISH_REASON_INVALID")
    content = message.get("content") or ""
    if scenario in {"tool-call", "tool-schema-check"}:
        calls = message.get("tool_calls", [])
        require(len(calls) == 1 and calls[0].get("id"), "TOOL_CALL_REQUIRED")
        function = calls[0].get("function", {})
        require(function.get("name") == "get_order", "TOOL_NOT_ALLOWED")
        require(
            json.loads(function.get("arguments", "null")) == {"order_id": "S1002"},
            "TOOL_ARGUMENTS_INVALID",
        )
    elif scenario == "validated-json":
        cleaned = content.strip()
        if cleaned.startswith("```json") and cleaned.endswith("```"):
            cleaned = cleaned[7:-3].strip()
        require(
            json.loads(cleaned) == {"action": "query", "order_id": "S1002"}, "OUTPUT_SCHEMA_INVALID"
        )
    elif scenario in {"plain-text", "stream-usage"}:
        require(content.strip().strip(".!。！").upper() == "OK", "TEXT_CONTENT_INVALID")
    elif scenario == "tool-result":
        require(bool(content.strip()) and not message.get("tool_calls"), "TOOL_RESULT_NOT_CONSUMED")
        require(
            "S1002" in content or "DELIVERED" in content or "送达" in content,
            "TOOL_RESULT_CONTENT_INVALID",
        )
    return {"returned_model": list(models)[0], "finish_reason": finishes[-1]}


def run_smoke(settings, approval_path, account_path):
    plan_path = PROJECT_ROOT / "evaluation/manifests/compatibility-smoke.json"
    plan = json.loads(plan_path.read_text())
    approval = json.loads(Path(approval_path).read_text())
    account = json.loads(Path(account_path).read_text())
    digest = validate_authorization(settings, approval, account, plan)
    directory = PROJECT_ROOT / "runtime/phase-06A"
    directory.mkdir(parents=True, exist_ok=True)
    state_path = directory / "batch-state.json"
    sessions = session_factory(settings)
    ledger = BudgetLedger(sessions)
    # Session-level lock forbids simultaneous batch runners, including separate CLI processes.
    with sessions.kw["bind"].connect() as lock:
        require(lock.scalar(text("SELECT pg_try_advisory_lock(62006001)")), "BATCH_ALREADY_RUNNING")
        try:
            require(not state_path.exists(), "BATCH_ALREADY_STARTED_REVIEW_AUDIT_BEFORE_ANY_RETRY")
            with sessions() as session:
                existing = session.scalar(
                    select(ModelCall.id).where(
                        ModelCall.batch_id == BATCH,
                        ModelCall.provider == "bailian-beijing-compatible",
                    )
                )
            require(existing is None, "EXISTING_BATCH_CALLS_REQUIRE_RECONCILIATION")
            conv = BusinessService(sessions).create_conversation("alice")
            state = {
                "batch_id": BATCH,
                "plan_sha256": digest,
                "started_at": now(),
                "status": "RUNNING",
                "max_http_requests": 8,
                "token_cap": 20000,
                "account_confirmation_source": (
                    "Explicit user confirmation; provider control plane not independently queried"
                ),
                "conversation_id": conv,
                "requests": [],
                "stop_reason": None,
            }
            write_json(state_path, state)
            started = time.monotonic()
            deadline = started + 600
            for row in plan["requests"]:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or len(state["requests"]) >= 8:
                    state["stop_reason"] = "BATCH_LIMIT"
                    break
                payload = row["request"]
                require(
                    payload["model"] == MODEL
                    and payload["max_tokens"] <= 128
                    and payload["enable_thinking"] is False,
                    "REQUEST_OUTSIDE_APPROVAL",
                )
                wire = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
                require(len(wire) + 1024 <= row["input_bound"], "INPUT_BOUND_EXCEEDED")
                call_id = ledger.reserve(
                    "bailian-beijing-compatible",
                    MODEL,
                    BATCH,
                    conv,
                    "compatibility-smoke-approved",
                    row["input_bound"],
                    row["output_cap"],
                    20000,
                )
                entry = {
                    "scenario": row["scenario"],
                    "call_id": call_id,
                    "reserved_tokens": row["reserved_bound"],
                    "status": "DISPATCHING",
                    "input_tokens": None,
                    "output_tokens": None,
                    "request_id": None,
                }
                state["requests"].append(entry)
                write_json(state_path, state)  # Counts this attempt before any possible HTTP.
                request_started = time.monotonic()
                try:
                    result = bounded(
                        send_once,
                        (
                            settings.dashscope_base_url.get_secret_value().rstrip("/"),
                            settings.dashscope_api_key.get_secret_value(),
                            payload,
                        ),
                        seconds=min(60, remaining),
                    )
                    write_json(
                        directory / f"{len(state['requests']):02d}-{row['scenario']}.json", result
                    )
                    entry.update(
                        http_status=result.get("http_status"), request_id=result.get("request_id")
                    )
                    require(
                        result.get("http_status") == 200,
                        "HTTP_" + str(result.get("http_status", "TRANSPORT_ERROR")),
                    )
                    incoming, outgoing, total = parse_usage(result.get("usage"))
                    ledger.settle(call_id, total, request_id=result.get("request_id"))
                    entry.update(
                        input_tokens=incoming,
                        output_tokens=outgoing,
                        request_id=result.get("request_id"),
                        http_status=result.get("http_status"),
                    )
                    require(outgoing <= row["output_cap"], "OUTPUT_CAP_EXCEEDED")
                    entry.update(validate_response(row["scenario"], result))
                    entry["status"] = "PASSED"
                except BaseException as error:
                    with sessions() as session:
                        settled = session.get(ModelCall, call_id).status == "SETTLED"
                    if not settled:
                        ledger.settle(call_id, None)
                    entry["status"] = "FAILED" if settled else "USAGE_UNKNOWN"
                    # Only stable business error code/type; never log network exception text.
                    entry["error_code"] = getattr(error, "code", type(error).__name__)
                    state["stop_reason"] = entry["error_code"]
                entry["elapsed_seconds"] = round(time.monotonic() - request_started, 3)
                write_json(state_path, state)
                if state["stop_reason"]:
                    break
            state["elapsed_seconds"] = round(time.monotonic() - started, 3)
            state["status"] = "STOPPED" if state["stop_reason"] else "COMPLETED"
            state["actual_http_dispatch_attempts"] = len(state["requests"])
            state["input_tokens"] = sum(r["input_tokens"] or 0 for r in state["requests"])
            state["output_tokens"] = sum(r["output_tokens"] or 0 for r in state["requests"])
            state["unknown_reserved_tokens"] = sum(
                r["reserved_tokens"] for r in state["requests"] if r["status"] == "USAGE_UNKNOWN"
            )
            state["not_run"] = [
                r["scenario"]
                for r in plan["requests"]
                if r["scenario"] not in {a["scenario"] for a in state["requests"]}
            ]
            state["known_input_tokens"] = state["input_tokens"]
            state["known_output_tokens"] = state["output_tokens"]
            state["usage_complete"] = state["unknown_reserved_tokens"] == 0
            if not state["usage_complete"]:
                state["input_tokens"] = None
                state["output_tokens"] = None
            state["http_responses_received"] = sum(
                r.get("http_status") is not None for r in state["requests"]
            )
            state["extra_paid_budget_cny"] = 0
            state["billing_note"] = (
                "Provider-reported usage; billing not queried. "
                "Free-tier protection and balance confirmed by user."
            )
            write_json(state_path, state)
            return state
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(62006001)"))
            lock.commit()
            sessions.kw["bind"].dispose()
