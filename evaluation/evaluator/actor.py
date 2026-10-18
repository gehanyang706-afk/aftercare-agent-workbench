"""Isolated product actor. Receives observable commands only, never scenario goals/oracles."""

import json
import sys
from datetime import datetime

from aftercare.agent.runtime import run_turn
from aftercare.config import Settings
from aftercare.offline import install_offline_guard
from aftercare.repositories.database import session_factory
from aftercare.services.business import BusinessService


def main():
    install_offline_guard()
    for line in sys.stdin:
        command = json.loads(line)
        try:
            settings = Settings(_env_file=None, database_url=command["database_url"])
            sessions = session_factory(settings)
            service = BusinessService(
                sessions, lambda clock=command["clock"]: datetime.fromisoformat(clock)
            )
            if command.get("commit_fault"):
                service.commit_fault = command["commit_fault"]
            from aftercare.llm.budget import BudgetLedger
            from aftercare.llm.scripted import ScriptedModel, offline_plan, offline_preview_stop

            mode = command.get("scripted_model_mode", "default")
            if mode not in {"default", "preview-stop"}:
                raise ValueError("UNKNOWN_OFFLINE_MODEL_MODE")
            revision = service.snapshot(command["principal"], command["conversation"])["revision"]
            model = ScriptedModel(
                ledger=BudgetLedger(sessions),
                conversation_id=command["conversation"],
                run_id=f"offline:{command['conversation']}:{revision}",
                planner=offline_preview_stop if mode == "preview-stop" else offline_plan,
            )
            result = run_turn(
                settings,
                service,
                command["principal"],
                command["conversation"],
                message_id=command.get("message_id"),
                resume=command.get("resume", False),
                decision=command.get("decision", "approve"),
                confirmation=command.get("confirmation"),
                profile=command["profile"],
                model=model,
            )
            texts = result.get("communications", [])
            output = {
                "ok": True,
                "communications": texts,
                "interrupted": bool(result.get("__interrupt__")),
            }
            sessions.kw["bind"].dispose()
        except Exception as e:
            output = {"ok": False, "error": type(e).__name__ + ":" + str(e)[:200]}
        print(json.dumps(output, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
