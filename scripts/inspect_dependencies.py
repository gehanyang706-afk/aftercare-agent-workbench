"""Inspect installed APIs without constructing a model or contacting a provider."""

import importlib.metadata as metadata
import inspect
import json
import platform
from pathlib import Path

from deepagents import create_deep_agent
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command, interrupt
from packaging.markers import default_environment
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
names = [
    "deepagents",
    "langgraph",
    "langchain",
    "langchain-core",
    "langgraph-checkpoint-postgres",
    "psycopg",
    "psycopg-binary",
    "psycopg-pool",
    "sqlalchemy",
    "alembic",
    "pgvector",
    "fastapi",
    "pydantic",
    "pydantic-settings",
    "uvicorn",
    "pytest",
    "ruff",
    "pip-tools",
]
apis = [create_deep_agent, PostgresSaver.from_conn_string, PostgresSaver.setup, interrupt, Command]
target = {
    **default_environment(),
    "sys_platform": "linux",
    "platform_machine": "aarch64",
    "platform_system": "Linux",
    "extra": "",
}
missing = []
queue = [
    Requirement(raw)
    for raw in metadata.requires("aftercare-agent-workbench") or []
    if not Requirement(raw).marker
    or any(Requirement(raw).marker.evaluate({**target, "extra": extra}) for extra in ["", "dev"])
]
seen = set()
while queue:
    requirement = queue.pop()
    identity = (requirement.name, tuple(sorted(requirement.extras)))
    if identity in seen:
        continue
    seen.add(identity)
    try:
        version = metadata.version(requirement.name)
    except metadata.PackageNotFoundError:
        missing.append(f"{requirement.name}: missing")
        continue
    if not requirement.specifier.contains(version, prereleases=True):
        missing.append(f"{requirement.name}: incompatible")
    for raw in metadata.requires(requirement.name) or []:
        child = Requirement(raw)
        if not child.marker or any(
            child.marker.evaluate({**target, "extra": extra})
            for extra in (requirement.extras or {""})
        ):
            queue.append(child)
result = {
    "python": platform.python_version(),
    "platform": platform.platform(),
    "packages": {
        name: {
            "version": metadata.version(name),
            "requires_python": metadata.metadata(name).get("Requires-Python"),
            "requires_dist": metadata.requires(name),
        }
        for name in names
    },
    "apis": {
        api.__qualname__: {
            "signature": str(inspect.signature(api)),
            "source_file": inspect.getsourcefile(api),
        }
        for api in apis
    },
    "verification_scope": "imports and signatures only; no agent or model constructed",
    "linux_aarch64_dependency_marker_check": {
        "missing_or_incompatible": missing,
        "wheel_install_tested": False,
    },
}
(ROOT / "docs/dependency-api.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n"
)
if missing:
    raise SystemExit("Linux dependency marker closure check failed")
