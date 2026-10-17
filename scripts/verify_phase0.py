"""Run phase-0 checks and a real loopback HTTP startup probe; no model traffic."""

import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "runtime/phase-00"
OUTPUT.mkdir(parents=True, exist_ok=True)
PYTHON = sys.executable
ENV = {
    **os.environ,
    "ALLOW_REAL_MODEL_CALLS": "false",
    "DATABASE_URL": "postgresql+psycopg://u:p@127.0.0.1:1/aftercare_test",
    "DASHSCOPE_API_KEY": "",
    "DASHSCOPE_BASE_URL": "",
}


def run(name: str, arguments: list[str], expected: int = 0) -> dict:
    result = subprocess.run(
        arguments, cwd=ROOT, env=ENV, capture_output=True, text=True, timeout=120
    )
    log = OUTPUT / f"{name}.log"
    log.write_text(result.stdout + result.stderr)
    return {
        "command": arguments,
        "exit_code": result.returncode,
        "expected_exit": expected,
        "passed": result.returncode == expected,
        "output": str(log.relative_to(ROOT)),
        "output_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
    }


def startup() -> dict:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    command = [PYTHON, "-m", "aftercare", "serve", "--offline", "--port", str(port)]
    with (OUTPUT / "startup.log").open("w") as log:
        process = subprocess.Popen(command, cwd=ROOT, env=ENV, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("service exited during startup")
                try:
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/health/live", timeout=1
                    ) as r:
                        live_status, live_body = r.status, json.load(r)
                    break
                except urllib.error.URLError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("service startup deadline exceeded")
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/health/ready", timeout=5)
                raise RuntimeError("unavailable database incorrectly ready")
            except urllib.error.HTTPError as error:
                ready_status, ready_body = error.code, json.load(error)
            assert live_status == 200 and ready_status == 503
            assert ready_body["code"] == "DATABASE_UNAVAILABLE"
            return {
                "command": command,
                "passed": True,
                "live": {"status": live_status, "body": live_body},
                "ready": {"status": ready_status, "body": ready_body},
                "database_fixture": "intentionally unavailable loopback port 1",
                "output": "runtime/phase-00/startup.log",
            }
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def main() -> int:
    results = {
        "pip_check": run("pip-check", [PYTHON, "-m", "pip", "check"]),
        "lint": run("ruff-check", [PYTHON, "-m", "ruff", "check", "."]),
        "format": run("ruff-format", [PYTHON, "-m", "ruff", "format", "--check", "."]),
        "tests": run(
            "pytest",
            [
                PYTHON,
                "-m",
                "pytest",
                "-m",
                "not live_model and not model_weights",
                "--junitxml=runtime/phase-00/junit.xml",
            ],
        ),
        "doctor_unavailable": run("doctor", [PYTHON, "-m", "aftercare", "doctor", "--offline"], 1),
        "compose": run("compose", ["docker", "compose", "config", "--quiet"]),
        "http_startup": startup(),
    }
    results["hashes"] = {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in [ROOT / "requirements.lock", ROOT / "compose.yaml", ROOT / "Dockerfile"]
    }
    results["real_model_requests"] = 0
    results["database_integration"] = "skipped: dedicated PostgreSQL not provisioned"
    passed = all(
        value["passed"]
        for value in results.values()
        if isinstance(value, dict) and "passed" in value
    )
    results["passed_available_phase0_checks"] = passed
    (ROOT / "docs/validation-phase-00.json").write_text(json.dumps(results, indent=2) + "\n")
    print(
        json.dumps(
            {"passed_available_phase0_checks": passed, "report": "docs/validation-phase-00.json"}
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
