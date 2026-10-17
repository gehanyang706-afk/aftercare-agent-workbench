"""Freeze offline RC from source hashes and public holdout attestation, never holdout answers."""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    files = []
    for directory in ("src", "configs", "data", "migrations", "evaluation", "scripts", "tests"):
        for path in (ROOT / directory).rglob("*"):
            if (
                path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix
                in {".py", ".json", ".jsonl", ".yaml", ".html", ".css", ".js", ".sql", ".md"}
            ):
                if path.name != "release-candidate.json":
                    files.append(path)
    for name in (
        "requirements.lock",
        "pyproject.toml",
        "Dockerfile",
        "compose.yaml",
        ".dockerignore",
        "alembic.ini",
    ):
        files.append(ROOT / name)
    files.extend((ROOT / "docs/experiments").glob("development-*"))
    hashes = {str(p.relative_to(ROOT)): sha(p) for p in sorted(files)}
    public = json.loads((ROOT / "evaluation/manifests/holdout-manifest.json").read_text())
    assert public["scenario_count"] == 100
    report = json.loads((ROOT / "docs/experiments/development-final.json").read_text())
    image = (ROOT / "runtime/phase-05/image-id.txt").read_text().strip()
    manifest = {
        "release": "offline-rc-phase-05",
        "real_model_calls": 0,
        "git_parent": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "source_tree_sha256": hashlib.sha256(
            json.dumps(hashes, sort_keys=True).encode()
        ).hexdigest(),
        "files": hashes,
        "app_image_id": image,
        "base_images": json.loads((ROOT / "configs/images.lock.json").read_text()),
        "local_weights": json.loads((ROOT / "configs/local-models.lock.json").read_text()),
        "development": {
            "count": report["attempted_tasks"],
            "passed": report["passed_tasks"],
            "provider": report["provider"],
        },
        "holdout": public,
        "holdout_answers_read_by_implementer": False,
        "task_sampling": (
            "No holdout execution. Future proposed stratified paired sample "
            "must be frozen before authorization."
        ),
        "model": "aftercare:scripted",
        "user": "adaptive-scripted-v1",
        "cache": "per-process 256 retrieval entries, key includes corpus/model/version/query",
        "limits": {
            "model_calls_per_run": 8,
            "per_conversation": 16,
            "conversation_token_cap": 100000,
            "scripted_batch_token_cap": 200000,
            "model_output_cap": 512,
            "actor_turn_seconds": 180,
        },
        "comparison_candidates": ["react-full-policy", "full"],
        "scope": "Offline engineering RC; no real-model quality/cost/generalization claim",
    }
    path = ROOT / "evaluation/manifests/release-candidate.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "manifest": str(path),
                "files": len(hashes),
                "tree_sha256": manifest["source_tree_sha256"],
                "image_id": image,
            }
        )
    )


if __name__ == "__main__":
    main()
