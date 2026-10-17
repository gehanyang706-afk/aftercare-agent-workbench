import json
from copy import deepcopy

import pytest
from sqlalchemy import select

from aftercare.config import PROJECT_ROOT, Settings
from aftercare.domain.contracts import BusinessError
from aftercare.llm import smoke
from aftercare.repositories.models import Budget, ModelCall


@pytest.fixture
def setup_smoke(service, tmp_path, monkeypatch):
    plan = json.loads((PROJECT_ROOT / "evaluation/manifests/compatibility-smoke.json").read_text())
    directory = tmp_path / "evaluation/manifests"
    directory.mkdir(parents=True)
    (directory / "compatibility-smoke.json").write_text(json.dumps(plan))
    approval = {
        "source": "Explicit user message in this chat",
        "plan_sha256": smoke.APPROVED_HASH,
        "batch_id": smoke.BATCH,
        "exact_model": smoke.MODEL,
        "max_http_requests_including_retries": 8,
        "total_token_cap": 20000,
        "concurrency": 1,
        "wall_clock_seconds": 600,
        "additional_paid_cost_cap_cny": 0,
    }
    account = {
        "plan_sha256": smoke.APPROVED_HASH,
        "beijing_key_confirmed": True,
        "free_tier_only_confirmed": True,
        "sufficient_quota_confirmed": True,
    }
    approval_path, account_path = tmp_path / "approval.json", tmp_path / "account.json"
    approval_path.write_text(json.dumps(approval))
    account_path.write_text(json.dumps(account))
    monkeypatch.setattr(smoke, "PROJECT_ROOT", tmp_path)
    settings = Settings(
        _env_file=None,
        allow_real_model_calls=True,
        database_url=service.sessions.kw["bind"].url.render_as_string(hide_password=False),
        dashscope_api_key="not-a-key",
        dashscope_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    return settings, approval_path, account_path, plan


def mock_response(payload):
    usage = {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}
    content = "OK"
    calls = None
    if payload.get("tools"):
        if any(m["role"] == "tool" for m in payload["messages"]):
            content = "S1002 DELIVERED"
        else:
            calls = [
                {
                    "id": "test-call",
                    "function": {"name": "get_order", "arguments": '{"order_id":"S1002"}'},
                }
            ]
    elif "Return JSON" in payload["messages"][0]["content"]:
        content = '{"action":"query","order_id":"S1002"}'
    if payload.get("stream"):
        return {
            "http_status": 200,
            "request_id": "mock",
            "usage": usage,
            "stream_done": True,
            "events": [
                {
                    "model": smoke.MODEL,
                    "choices": [{"delta": {"content": "OK"}, "finish_reason": "stop"}],
                },
                {"usage": usage, "choices": []},
            ],
        }
    return {
        "http_status": 200,
        "request_id": "mock",
        "usage": usage,
        "data": {
            "model": smoke.MODEL,
            "choices": [
                {
                    "message": {"content": content, "tool_calls": calls},
                    "finish_reason": "tool_calls" if calls else "stop",
                }
            ],
        },
    }


def test_mock_batch_and_rerun_are_bounded(setup_smoke, monkeypatch):
    settings, approval, account, _ = setup_smoke
    seen = []

    def bounded_mock(fn, args, seconds):
        assert seconds <= 60
        seen.append(args[2])
        return mock_response(args[2])

    monkeypatch.setattr(smoke, "bounded", bounded_mock)
    result = smoke.run_smoke(settings, approval, account)
    assert result["status"] == "COMPLETED"
    assert len(seen) == result["actual_http_dispatch_attempts"] == 6
    assert result["input_tokens"] == 600 and result["output_tokens"] == 60
    with pytest.raises(BusinessError, match="BATCH_ALREADY_STARTED"):
        smoke.run_smoke(settings, approval, account)
    assert len(seen) == 6


@pytest.mark.parametrize("failure", ["unknown", "protocol", "timeout"])
def test_unknown_or_protocol_failure_stops_immediately(setup_smoke, monkeypatch, service, failure):
    settings, approval, account, _ = setup_smoke

    def failed(fn, args, seconds):
        if failure == "timeout":
            raise TimeoutError("hard cutoff")
        if failure == "unknown":
            return {"http_status": 403, "usage": None, "error": "HTTP_ERROR"}
        result = mock_response(args[2])
        result["data"]["choices"][0]["message"]["content"] = "unexpected"
        return result

    monkeypatch.setattr(smoke, "bounded", failed)
    result = smoke.run_smoke(settings, approval, account)
    assert result["status"] == "STOPPED" and len(result["requests"]) == 1
    assert len(result["not_run"]) == 5
    with service.sessions() as s:
        call = s.scalar(select(ModelCall))
        if failure in {"unknown", "timeout"}:
            assert call.status == "USAGE_UNKNOWN"
            assert s.get(Budget, call.budget_id).paused
            assert result["unknown_reserved_tokens"] > 0
        else:
            assert call.status == "SETTLED" and call.usage == 110


def test_unconfirmed_or_modified_plan_denied_without_send(setup_smoke):
    settings, approval_path, account_path, plan = setup_smoke
    approval = json.loads(approval_path.read_text())
    account = json.loads(account_path.read_text())
    account["free_tier_only_confirmed"] = False
    with pytest.raises(BusinessError, match="ACCOUNT_PROTECTION"):
        smoke.validate_authorization(settings, approval, account, plan)
    account["free_tier_only_confirmed"] = True
    changed = deepcopy(plan)
    changed["requests"][0]["request"]["model"] = "different-model"
    with pytest.raises(BusinessError, match="HASH_MISMATCH"):
        smoke.validate_authorization(settings, approval, account, changed)


def test_stream_requires_done_and_consistent_usage():
    result = mock_response({"stream": True, "messages": [{"role": "user", "content": "OK"}]})
    result["stream_done"] = False
    with pytest.raises(BusinessError, match="STREAM_INCOMPLETE"):
        smoke.validate_response("stream-usage", result)
    with pytest.raises(BusinessError, match="USAGE_TOTAL"):
        smoke.parse_usage({"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 3})
