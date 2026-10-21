"""Real loopback service process restarts, controlled Qloo replay outage, no live calls."""

import json
import os
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import httpx

from backend.tests.test_service import choose

ROOT = Path(__file__).resolve().parents[1]


def main():
    result = {
        "kind": "real_service_process_restarts_with_captured_http_replay",
        "live_provider_requests": 0,
        "checks": [],
    }
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="cultural-recovery-", dir=ROOT / "reports/local") as directory:
        folder = Path(directory)
        headers = {"Authorization": "Bearer " + secrets.token_urlsafe(32)}
        body = {
            "request_id": str(uuid4()),
            "mode": "cultural",
            "interests": [{"name": "David Bowie", "category": "artist"}],
        }
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=10) as client:

            def start(fault=""):
                env = {
                    **os.environ,
                    "IS_CAPTURE_REPLAY_ONLY": "1",
                    "IS_CAPTURE_REPLAY_DIRECTORY": str(folder),
                    "IS_CAPTURE_REPLAY_FAULT": fault,
                    "PYTHONDONTWRITEBYTECODE": "1",
                }
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "scripts.local_cultural_verification:create_verification_app",
                        "--factory",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(port),
                        "--no-access-log",
                    ],
                    cwd=ROOT,
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError("Isolated replay service failed to start")
                    try:
                        if client.get("/healthz").status_code == 200:
                            return process
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.1)
                process.terminate()
                process.wait(timeout=10)
                raise RuntimeError("Isolated replay startup timeout")

            def stop(process):
                process.terminate()
                process.wait(timeout=10)

            def budget():
                with sqlite3.connect(folder / "sessions.sqlite3") as db:
                    return db.execute("SELECT sum(used) FROM qloo_daily_budget").fetchone()[0]

            process = start()
            try:
                created = client.post("/v1/sessions", headers=headers, json=body)
                assert created.status_code == 200
                prior = choose(client, headers, created.json(), "mara", "take_map")
                assert budget() == 2
            finally:
                stop(process)
            process = start("503")
            try:
                failed = {**body, "request_id": str(uuid4())}
                error = client.post("/v1/sessions", headers=headers, json=failed)
                assert error.json()["error"]["code"] == "QLOO_UPSTREAM" and budget() == 4
                assert client.post("/v1/sessions", headers=headers, json=failed).status_code == 503 and budget() == 4
                loaded = client.get("/v1/sessions/" + prior["session_id"], headers=headers).json()
                assert loaded["state"] == prior["state"] and loaded["revision"] == prior["revision"]
                result["checks"].append(
                    "Controlled Insights503 after resolution preserves saved cultural quest; duplicate failed creation makes no new transport calls"
                )
            finally:
                stop(process)
            process = start()
            try:
                loaded = client.get("/v1/sessions/" + prior["session_id"], headers=headers).json()
                assert loaded["state"] == prior["state"] and loaded["revision"] == prior["revision"] and budget() == 4
                assert client.post("/v1/sessions", headers=headers, json=failed).status_code == 503 and budget() == 4
                good = client.post("/v1/sessions", headers=headers, json={**body, "request_id": str(uuid4())})
                assert good.status_code == 200 and budget() == 6
                result["checks"].append(
                    "Actual service stop/start after failed operation preserves exact saved state and terminal failed receipt"
                )
                result["checks"].append(
                    "Provider replay recovery allows new deliberate creation, exactly two mock requests, no duplicate progress"
                )
            finally:
                stop(process)
    result["status"] = "PASS"
    result["mock_http_requests"] = 6
    result["owned_processes_stopped"] = True
    result["private_temporary_database_removed"] = True
    path = ROOT / "reports/CULTURAL_PROCESS_RECOVERY_20261020.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
