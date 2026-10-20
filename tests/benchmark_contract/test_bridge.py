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
