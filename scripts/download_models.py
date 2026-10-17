"""Download only the approved files, at immutable revisions, into this project."""

import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = {
    "embedding": {
        "repo": "BAAI/bge-small-zh-v1.5",
        "revision": "7999e1d3359715c523056ef9478215996d62a620",
        "files": [
            "config.json",
            "model.safetensors",
            "tokenizer.json",
            "tokenizer_config.json",
            "special_tokens_map.json",
            "vocab.txt",
        ],
    },
    "reranker": {
        "repo": "BAAI/bge-reranker-base",
        "revision": "2cfc18c9415c912f9d8155881c133215df768a70",
        "files": [
            "config.json",
            "onnx/model.onnx",
            "tokenizer.json",
            "tokenizer_config.json",
            "special_tokens_map.json",
        ],
    },
}


def main():
    records = {}
    total = 0
    for role, model in MODELS.items():
        records[role] = {**model, "artifacts": []}
        for name in model["files"]:
            destination = ROOT / "runtime/models" / role / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                partial = destination.with_suffix(destination.suffix + ".partial")
                url = f"https://huggingface.co/{model['repo']}/resolve/{model['revision']}/{name}"
                with urllib.request.urlopen(url, timeout=60) as r, partial.open("wb") as f:
                    while block := r.read(1024 * 1024):
                        total += len(block)
                        if total > 1_500_000_000:
                            raise RuntimeError("DOWNLOAD_CAP_EXCEEDED")
                        f.write(block)
                partial.replace(destination)
            records[role]["artifacts"].append(
                {
                    "file": name,
                    "bytes": destination.stat().st_size,
                    "sha256": hashlib.file_digest(destination.open("rb"), "sha256").hexdigest(),
                }
            )
            print(role, name, destination.stat().st_size, flush=True)
    (ROOT / "configs/local-models.lock.json").write_text(json.dumps(records, indent=2) + "\n")


if __name__ == "__main__":
    main()
