"""Read source/split metadata, never expose task payloads to an agent factory."""

import hashlib
import json
import subprocess
from pathlib import Path

from aftercare.harness.contracts import digest

ROOT = Path(__file__).resolve().parents[3]
LOCK = ROOT / "benchmarks/tau_retail/upstream.lock.json"


def upstream():
    lock = json.loads(LOCK.read_text())
    root = ROOT / lock["local_source"]
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if head != lock["commit"]:
        raise ValueError("UPSTREAM_COMMIT_MISMATCH")
    for path, expected in lock["source_hashes"].items():
        if hashlib.sha256((root / path).read_bytes()).hexdigest() != expected:
            raise ValueError("UPSTREAM_CONTENT_CHANGED:" + path)
    return root


def source_fingerprint():
    paths = []
    for folder in ("src", "evaluation/benchmarks", "evaluation/reliability", "migrations"):
        paths += [p for p in (ROOT / folder).rglob("*.py") if "__pycache__" not in p.parts]
    paths += [ROOT / "benchmarks/tau_retail/requirements.lock", LOCK]
    return digest(
        {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths)
        }
    )


def load_train_tasks(task_ids):
    root = upstream()
    split = json.loads((root / "data/tau2/domains/retail/split_tasks.json").read_text())
    if not set(task_ids) <= set(split["train"]):
        raise ValueError("ONLY_FROZEN_TRAIN_TASKS_ALLOWED")
    # Trusted loader: discard non-selected payloads without logging or exporting them.
    all_tasks = json.loads((root / "data/tau2/domains/retail/tasks.json").read_text())
    from tau2.data_model.tasks import Task

    selected = {t["id"]: Task.model_validate(t) for t in all_tasks if t["id"] in task_ids}
    return [selected[k] for k in task_ids]
