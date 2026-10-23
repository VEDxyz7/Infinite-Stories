"""Real disposable PostgreSQL: integration tests, server restart, dump and restore.

Uses only a private Unix socket; never reads .env or connects to an existing DB.
Run with Python from the project venv. Requires installed PostgreSQL binaries.
"""

import argparse
import json
import os
import secrets
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bin-dir", type=Path, default=Path("/opt/homebrew/opt/postgresql@17/bin"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Evidence exists; refusing to overwrite it")
    for name in ("postgres", "initdb", "pg_ctl", "createdb", "pg_dump", "pg_restore"):
        if not (args.bin_dir / name).is_file():
            raise SystemExit("Required PostgreSQL binaries are unavailable")
    report = {"kind": "real_disposable_postgresql", "provider_requests": 0, "checks": []}

    def run(name, *arguments):
        result = subprocess.run([str(args.bin_dir / name), *map(str, arguments)], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError("PostgreSQL verification step failed: " + name)
        return result.stdout.strip()

    tmp_root = "/private/tmp" if Path("/private/tmp").is_dir() else "/tmp"
    with tempfile.TemporaryDirectory(prefix="is-pg-", dir=tmp_root) as folder:
        work = Path(folder)
        data, sock = work / "db", work / "socket"
        sock.mkdir(mode=0o700)
        running = False
        try:
            run("initdb", "-D", data, "-U", "stories", "-A", "trust", "--no-locale", "-E", "UTF8")
            with (data / "postgresql.conf").open("a") as config:
                config.write(
                    f"\nlisten_addresses=''\nport=55433\nunix_socket_directories='{sock}'\nunix_socket_permissions=0700\n"
                )
            run("pg_ctl", "-D", data, "-l", work / "server.log", "-w", "start")
            running = True
            connection = ["-h", str(sock), "-p", "55433", "-U", "stories"]
            run("createdb", *connection, "stories_test")
            url = f"postgresql+psycopg://stories@/stories_test?host={sock}&port=55433"
            test_env = {**os.environ, "IS_TEST_POSTGRES_URL": url}
            tests = subprocess.run(
                [os.sys.executable, "-m", "pytest", "backend/tests", "-q", "-p", "no:cacheprovider"],
                cwd=ROOT,
                env=test_env,
                capture_output=True,
                text=True,
            )
            if tests.returncode:
                raise RuntimeError("Real PostgreSQL integration tests failed")
            report["pytest_summary"] = tests.stdout.strip().splitlines()[-1]
            report["checks"].append(
                "Full backend suite passed with real PostgreSQL enabled, including four-category cultural creation/quest/restart integration"
            )
            settings = Settings(database_url=url, environment="test")
            headers = {"Authorization": "Bearer " + secrets.token_urlsafe(32)}
            with TestClient(create_app(settings)) as client:
                response = client.post(
                    "/v1/sessions", headers=headers, json={"mode": "authored", "request_id": str(uuid4())}
                )
                if response.status_code != 200:
                    raise RuntimeError("Could not create recovery test journey")
                view = response.json()
                response = client.post(
                    "/v1/sessions/" + view["session_id"] + "/actions",
                    headers=headers,
                    json={
                        "request_id": str(uuid4()),
                        "expected_revision": 0,
                        "command": {"kind": "position", "x": 5, "y": 5},
                    },
                )
                if response.status_code != 200:
                    raise RuntimeError("Could not save recovery test journey")
                expected = response.json()
            # An actual procedural snapshot over explicitly captured Qloo data.
            # Transport is MockTransport; no event key or live request is used.
            from dataclasses import replace

            from backend.tests.test_cultural_production import harness

            cultural_config, provider, calls, interest, _ = harness(work / "captured-city", "brand")
            cultural_config = replace(cultural_config, database_url=url)
            with TestClient(create_app(cultural_config, cultural_provider=provider)) as client:
                created = client.post(
                    "/v1/sessions",
                    headers=headers,
                    json={"mode": "cultural", "request_id": str(uuid4()), "interests": [interest]},
                )
                if created.status_code != 200 or not created.json()["state"].get("city_generation"):
                    raise RuntimeError("Could not prepare procedural recovery snapshot")
                cultural_expected = created.json()
            if len(calls) != 2:
                raise RuntimeError("Captured transport operation count differs")
            run("pg_ctl", "-D", data, "-w", "stop")
            running = False
            run("pg_ctl", "-D", data, "-l", work / "server.log", "-w", "start")
            running = True

            def verify_snapshot(database):
                with TestClient(create_app(Settings(database_url=database, environment="test"))) as client:
                    restored = client.get("/v1/sessions/" + expected["session_id"], headers=headers)
                    if (
                        restored.status_code != 200
                        or restored.json()["state"] != expected["state"]
                        or restored.json()["revision"] != 1
                    ):
                        raise RuntimeError("Recovered journey differs from confirmed snapshot")
                    city = client.get("/v1/sessions/" + cultural_expected["session_id"], headers=headers)
                    if (
                        city.status_code != 200
                        or city.json()["state"] != cultural_expected["state"]
                        or city.json()["revision"] != cultural_expected["revision"]
                    ):
                        raise RuntimeError("Procedural seed/plan/proof snapshot changed on recovery")

            verify_snapshot(url)
            report["checks"].append("Confirmed snapshot and ownership survived actual PostgreSQL process restart")
            dump = work / "backup.dump"
            dump.touch(mode=0o600)
            run("pg_dump", *connection, "-Fc", "-f", dump, "stories_test")
            run("createdb", *connection, "stories_restored")
            run("pg_restore", *connection, "--exit-on-error", "-d", "stories_restored", dump)
            verify_snapshot(url.replace("/stories_test?", "/stories_restored?"))
            report["checks"].append(
                "pg_dump/pg_restore into a separate empty database preserved snapshot, revision and ownership"
            )
            report["checks"].append(
                "Captured-evidence procedural seed, plan, evidence and witness survived actual PostgreSQL restart and dump/restore without provider access"
            )
            report["postgres_version"] = run("postgres", "--version")
        finally:
            if running:
                run("pg_ctl", "-D", data, "-w", "stop")
    report["disposable_cluster_stopped_and_removed"] = True
    with args.output.open("x") as out:
        json.dump(report, out, indent=2)
        out.write("\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
