"""Resolve registry metadata only. Never download image layers or start containers."""

import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACCEPT = ", ".join(
    [
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    ]
)


def read(url: str, headers: dict | None = None) -> tuple[dict, object]:
    with urllib.request.urlopen(
        urllib.request.Request(url, headers=headers or {}), timeout=30
    ) as r:
        return json.load(r), r.headers


def resolve(repository: str, tag: str) -> dict:
    query = urllib.parse.urlencode(
        {
            "service": "registry.docker.io",
            "scope": f"repository:{repository}:pull",
        }
    )
    auth, _ = read(f"https://auth.docker.io/token?{query}")
    headers = {"Authorization": f"Bearer {auth['token']}", "Accept": ACCEPT}
    base = f"https://registry-1.docker.io/v2/{repository}/manifests/"
    index, response_headers = read(base + tag, headers)
    arm = next(
        m
        for m in index["manifests"]
        if m.get("platform", {}).get("os") == "linux"
        and m.get("platform", {}).get("architecture") == "arm64"
    )
    manifest, _ = read(base + arm["digest"], headers)
    return {
        "repository": repository,
        "tag": tag,
        "index_digest": response_headers["Docker-Content-Digest"],
        "arm64_digest": arm["digest"],
        "arm64_compressed_layer_bytes": sum(layer["size"] for layer in manifest["layers"]),
        "downloaded_layers": False,
    }


if __name__ == "__main__":
    result = {
        "python": resolve("library/python", "3.13.14-slim-bookworm"),
        "postgres": resolve("pgvector/pgvector", "pg17"),
    }
    (ROOT / "configs/images.lock.json").write_text(json.dumps(result, indent=2) + "\n")
