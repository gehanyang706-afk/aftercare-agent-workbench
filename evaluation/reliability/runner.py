"""Append-only fixed reliability run. Run serially; pytest must not share its test DB."""

import argparse
import fcntl
import hashlib
import json
import time
from pathlib import Path

from alembic import command
from alembic.config import Config

from aftercare.config import PROJECT_ROOT, Settings
from aftercare.offline import install_offline_guard
from aftercare.services.business import BusinessService
from evaluation.reliability.cases import TEST_URL, connect, reset, run_case
from evaluation.reliability.invariants import snapshot


def run(manifest_path, output=None):
    install_offline_guard()
    plan = json.loads(Path(manifest_path).read_text())
    from evaluation.benchmarks.tau_retail.source_guard import source_fingerprint

    if plan.get("kind") != "smoke":
        if plan["source_tree_hash"] != source_fingerprint():
            raise ValueError("RELIABILITY_SOURCE_HASH_MISMATCH")
        if [c["case_id"] for c in plan["cases"]] != [f"F{i:02}" for i in range(1, 13)]:
            raise ValueError("FIXED_12_GROUPS_REQUIRED")
        if any(c["repeats"] != 20 for c in plan["cases"]):
            raise ValueError("FIXED_20_REPEATS_REQUIRED")
    root = Path(output or PROJECT_ROOT / "runtime/reliability" / plan["run_id"])
    root.mkdir(parents=True, exist_ok=False)
    lock = (PROJECT_ROOT / "runtime/reliability-test.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.attributes["settings"] = Settings(_env_file=None, database_url=TEST_URL, app_env="test")
    command.upgrade(config, "head")
    sessions = connect()
    (root / "manifest.json").write_text(json.dumps(plan, indent=2) + "\n")
    rows = []
    try:
        for case in plan["cases"]:
            for repeat in range(case["repeats"]):
                reset(sessions)
                row = {
                    "case_id": case["case_id"],
                    "repeat": repeat,
                    "seed": plan["seed"] + repeat,
                    "concurrency": case["concurrency"],
                    "injection": case["injection"],
                    "source_tree_hash": plan["source_tree_hash"],
                    "inventory_and_counts_before": snapshot(sessions),
                    "triggered": False,
                    "passed": False,
                }
                start = time.monotonic()
                try:
                    row.update(run_case(BusinessService(sessions), case["case_id"]))
                    row["passed"] = True
                except Exception as e:
                    import traceback

                    row.update(
                        error=type(e).__name__ + ":" + str(e),
                        traceback=traceback.format_exc(),
                        evidence=getattr(e, "reliability_evidence", []),
                    )
                row["seconds"] = time.monotonic() - start
                rows.append(row)
                with (root / "results.jsonl").open("a") as f:
                    f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                print(
                    f"{case['case_id']} {repeat + 1}/{case['repeats']}: "
                    + ("PASS" if row["passed"] else row.get("error", "FAIL")),
                    flush=True,
                )
        summary = {
            "run_id": plan["run_id"],
            "planned": sum(c["repeats"] for c in plan["cases"]),
            "executed": len(rows),
            "passed": sum(r["passed"] for r in rows),
            "groups": {},
            "M": 0,
        }
        for c in plan["cases"]:
            group = [r for r in rows if r["case_id"] == c["case_id"]]
            passed = len(group) == 20 and all(r["passed"] and r["triggered"] for r in group)
            summary["groups"][c["case_id"]] = {"repetitions": len(group), "all20_passed": passed}
            summary["M"] += passed
        summary["results_sha256"] = hashlib.sha256(
            (root / "results.jsonl").read_bytes()
        ).hexdigest()
        (root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        return summary
    finally:
        sessions.kw["bind"].dispose()
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--offline", action="store_true", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    print(json.dumps(run(args.manifest, args.output), indent=2))


if __name__ == "__main__":
    main()
