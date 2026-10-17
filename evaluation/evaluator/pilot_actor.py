"""Product-only pilot actor: message IDs and operational context, never evaluator answers."""

import json
import sys
from datetime import datetime

from aftercare.agent.runtime import run_turn
from aftercare.config import Settings
from aftercare.llm.pilot_gateway import PilotGateway
from aftercare.llm.real import BudgetedBailianModel
from aftercare.offline import install_offline_guard
from aftercare.repositories.database import session_factory
from aftercare.services.business import BusinessService


def main():
    install_offline_guard()
    for line in sys.stdin:
        command = json.loads(line)
        service_sessions = ledger_sessions = None
        try:
            settings = Settings()
            business_settings = Settings(_env_file=None, database_url=command["database_url"])
            service_sessions = session_factory(business_settings)
            ledger_sessions = session_factory(settings)
            service = BusinessService(
                service_sessions, lambda clock=command["clock"]: datetime.fromisoformat(clock)
            )
            if command.get("commit_fault"):
                service.commit_fault = command["commit_fault"]
            snapshot = service.snapshot(command["principal"], command["conversation"])
            gateway = PilotGateway(
                settings,
                ledger_sessions,
                command["ledger_conversation"],
                service,
                command["principal"],
                command["conversation"],
                f"pilot:{command['ledger_conversation']}:{snapshot['revision']}",
                command["deadline"],
                command["trace_directory"],
                command["permit"],
            )
            result = run_turn(
                business_settings,
                service,
                command["principal"],
                command["conversation"],
                message_id=command.get("message_id"),
                resume=command.get("resume", False),
                decision=command.get("decision", "approve"),
                profile="full",
                model=BudgetedBailianModel(gateway=gateway),
            )
            output = {
                "ok": True,
                "communications": [
                    str(m.content)
                    for m in result.get("messages", [])
                    if m.type == "ai" and m.content
                ],
                "interrupted": bool(result.get("__interrupt__")),
            }
        except Exception as e:
            output = {"ok": False, "error": getattr(e, "code", type(e).__name__)}
        finally:
            for sessions in (service_sessions, ledger_sessions):
                if sessions is not None:
                    sessions.kw["bind"].dispose()
        print(json.dumps(output, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
