from aftercare.agent.runtime import run_turn
from aftercare.domain.rules import require


def run_agent_demo(settings, service, case):
    conv = service.create_conversation("alice")
    msg = service.append_message("alice", conv, "S1002 换大一码", "first")
    result = run_turn(settings, service, "alice", conv, msg["id"])
    require(bool(result.get("__interrupt__")), "EXPECTED_CONFIRMATION")
    pid = next(
        p["id"] for p in service.snapshot("alice", conv)["previews"] if p["status"] == "PENDING"
    )
    if case == "revise-before-confirm":
        msg = service.append_message("alice", conv, "改为退货", "second")
        run_turn(settings, service, "alice", conv, msg["id"])
        snapshot = service.snapshot("alice", conv)
        require(
            next(p for p in snapshot["previews"] if p["id"] == pid)["status"] == "INVALIDATED",
            "OLD_PREVIEW_NOT_INVALIDATED",
        )
        pid = next(p["id"] for p in snapshot["previews"] if p["status"] == "PENDING")
    service.confirm("alice", pid, True)
    if case == "restart-after-commit":
        service.commit("alice", pid)
    run_turn(settings, service, "alice", conv, resume=True)
    return service.get_operation("alice", preview_id=pid)
