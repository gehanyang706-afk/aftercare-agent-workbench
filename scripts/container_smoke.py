"""Local HTTP smoke against the actual Compose app + worker."""

import json
import time

import httpx

from aftercare.config import PROJECT_ROOT

base = "http://127.0.0.1:8128"
with httpx.Client(base_url=base, timeout=10) as client:
    ready = client.get("/health/ready")
    ready.raise_for_status()
    me = client.post("/api/demo-sessions", json={"customer_id": "alice"})
    me.raise_for_status()
    client.headers["X-CSRF-Token"] = me.json()["csrf_token"]
    conv = client.post("/api/conversations").json()["id"]
    r = client.post(
        f"/api/conversations/{conv}/messages",
        json={"text": "S1001 取消订单", "client_message_id": "container-smoke"},
    )
    r.raise_for_status()

    def wait(condition):
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            snap = client.get(f"/api/conversations/{conv}").json()
            if condition(snap):
                return snap
            if snap["status"] == "FAILED":
                raise AssertionError(snap)
            time.sleep(0.25)
        raise TimeoutError("COMPOSE_WORKER_DID_NOT_FINISH")

    snap = wait(lambda v: v["status"] == "WAITING_CONFIRMATION")
    pid = next(p["id"] for p in snap["previews"] if p["status"] == "PENDING")
    client.post(f"/api/previews/{pid}/confirm", json={"decision": "accept"}).raise_for_status()
    snap = wait(lambda v: bool(v["operations"]))
    client.post(f"/api/previews/{pid}/confirm", json={"decision": "accept"}).raise_for_status()
    again = client.get(f"/api/conversations/{conv}").json()
    assert len(again["operations"]) == 1 and again["operations"][0]["result"] == "CANCELLED"
    report = {
        "base_url": base,
        "ready_status": ready.status_code,
        "conversation_id": conv,
        "receipt": again["operations"][0],
        "duplicate_confirm_operations": len(again["operations"]),
        "remote_model_calls": 0,
        "worker": "Compose container (host worker stopped)",
    }
    target = PROJECT_ROOT / "docs/experiments/container-smoke.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))
