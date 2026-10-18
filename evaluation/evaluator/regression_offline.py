"""Seen development regressions only. No real-provider option exists in this entry."""

import argparse
import hashlib
import json
import os
import subprocess
import time

from aftercare.config import PROJECT_ROOT, Settings
from aftercare.offline import install_offline_guard
from aftercare.repositories.database import session_factory
from evaluation.evaluator.diagnostics_v3 import VERSION, diagnose, event_chain
from evaluation.evaluator.runner import Actor, run_case
from evaluation.evaluator.user_policy_v2 import VERSION as USER_VERSION
from evaluation.schema.scenario import Scenario

FILES = ("evaluation/dev/regression-v1.jsonl", "evaluation/dev/quantity-clarification-v1.jsonl")


def main():
    install_offline_guard()
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-mode", choices=["default", "preview-stop"], default="default")
    mode = parser.parse_args().model_mode

    class OfflineActor(Actor):
        def invoke(self, command):
            return super().invoke({**command, "scripted_model_mode": mode})

    settings = Settings(
        _env_file=None,
        database_url=os.environ.get(
            "AFTERCARE_TEST_DATABASE_URL",
            "postgresql+psycopg://aftercare:aftercare_local_only@127.0.0.1:55432/aftercare_test",
        ),
    )
    sessions = session_factory(settings)
    output = PROJECT_ROOT / "runtime/closure-repair" / ("offline-" + time.strftime("%Y%m%d-%H%M%S"))
    output.mkdir(parents=True)
    results = []
    for file in FILES:
        for line in (PROJECT_ROOT / file).read_text().splitlines():
            case = Scenario.model_validate_json(line)
            assert case.split == "dev"
            start = time.monotonic()
            result = run_case(case, settings, sessions, "full", output, actor_factory=OfflineActor)
            result["diagnostics"] = diagnose(result["observed"])
            result["event_chain"] = event_chain(result["observed"])
            result["elapsed_seconds"] = round(time.monotonic() - start, 3)
            (output / (case.scenario_id + ".json")).write_text(
                json.dumps(result, ensure_ascii=False, indent=2, default=str)
            )
            results.append(
                {
                    k: result[k]
                    for k in (
                        "scenario_id",
                        "result",
                        "diagnostics",
                        "event_chain",
                        "elapsed_seconds",
                    )
                }
            )
            print(case.scenario_id, result["result"]["success"], flush=True)
    summary = {
        "provider": "scripted",
        "model_mode": mode,
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "real_http_requests": 0,
        "holdout_access": False,
        "diagnostics_version": VERSION,
        "user_policy_version": USER_VERSION,
        "files": {f: hashlib.sha256((PROJECT_ROOT / f).read_bytes()).hexdigest() for f in FILES},
        "scorer_sha256": hashlib.sha256(
            (PROJECT_ROOT / "evaluation/evaluator/grader.py").read_bytes()
        ).hexdigest(),
        "output": str(output),
        "tasks": results,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str)
    )
    print(output)
    sessions.kw["bind"].dispose()


if __name__ == "__main__":
    main()
