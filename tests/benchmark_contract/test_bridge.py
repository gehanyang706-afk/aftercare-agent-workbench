import pytest

pytest.importorskip("tau2")
from evaluation.benchmarks.tau_retail import model_bridge


class Ledger:
    def __init__(self):
        self.events = []

    def reserve(self, *a):
        self.events.append(("reserve", a))
        return "call"

    def settle(self, *a):
        self.events.append(("settle", a))


class Trace:
    def emit(self, *a, **kw):
        pass


def bridge(monkeypatch, raw):
    monkeypatch.setattr(model_bridge, "role_at_boundary", lambda: "agent")
    ledger = Ledger()
    role = dict(enabled=True, exact_model="fixture", output_cap=100, request_seconds=1)
    obj = model_bridge.CompletionBridge(
        ledger, "run", "episode", {"agent": role}, lambda payload, timeout: raw, Trace(), 10**12
    )
    return obj, ledger


def test_usage_settled_before_bad_protocol(monkeypatch):
    obj, ledger = bridge(
        monkeypatch,
        {
            "model": "fixture",
            "choices": [],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        },
    )
    with pytest.raises(ValueError, match="INVALID_MODEL_PROTOCOL"):
        obj(model="fixture", messages=[], max_tokens=100, num_retries=0)
    assert ledger.events[-1][0] == "settle"
    assert ledger.events[-1][1][1] == 5


def test_unknown_reservation_never_zero(monkeypatch):
    obj, ledger = bridge(monkeypatch, {"choices": []})
    with pytest.raises(ValueError, match="USAGE_UNKNOWN"):
        obj(model="fixture", messages=[], max_tokens=100, num_retries=0)
    assert ledger.events[-1][1][1] is None
    with pytest.raises(ValueError, match="RETRY"):
        obj(model="fixture", messages=[], max_tokens=100, num_retries=1)


def test_native_mixed_message_is_preserved_and_raw_response_is_recorded(monkeypatch):
    raw = {
        "model": "fixture",
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": "I will check now.",
                    "tool_calls": [
                        {
                            "id": "native-read",
                            "type": "function",
                            "function": {"name": "calculate", "arguments": '{"expression":"2+2"}'},
                        }
                    ],
                },
            }
        ],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    }
    obj, ledger = bridge(monkeypatch, raw)
    events = []

    class CapturedTrace:
        def emit(self, event, payload, *args, **kwargs):
            events.append((event, payload))

    obj.trace = CapturedTrace()
    result = obj(model="fixture", messages=[], max_tokens=100, num_retries=0)
    assert result.choices[0].message.content == "I will check now."
    assert result.choices[0].message.tool_calls[0].id == "native-read"
    assert any(name == "model.received" and payload["response"] == raw for name, payload in events)
    assert any(name == "protocol.mixed_message" for name, _ in events)
    assert ledger.events[-1][1][1] == 5


def test_failed_response_keeps_safe_envelope_before_unknown_stop(monkeypatch):
    raw = {
        "http_status": 401,
        "request_id": "synthetic-request",
        "error": "HTTP_ERROR",
        "choices": [],
        "usage": None,
    }
    obj, ledger = bridge(monkeypatch, raw)
    events = []

    class CapturedTrace:
        def emit(self, event, payload, *args, **kwargs):
            events.append((event, payload))

    obj.trace = CapturedTrace()
    with pytest.raises(ValueError, match="USAGE_UNKNOWN"):
        obj(model="fixture", messages=[], max_tokens=100, num_retries=0)
    assert any(name == "model.received" and p["response"] == raw for name, p in events)
    assert ledger.events[-1][1][1] is None
