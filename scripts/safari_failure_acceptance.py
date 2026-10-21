"""Safari WebDriver recovery with isolated replay faults; never live providers.

Temporarily replaces only the verified loopback replay process, preserving its DB.
Leaves that replay service healthy, with no fault selected, for continued review.
"""

import argparse
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time

import httpx

from scripts.safari_replay_acceptance import PRIVATE, ROOT, Safari

FAULT_FILE = PRIVATE / "upstream-scenario"
DATABASE = ROOT / "reports/local/client-cultural-verification/sessions.sqlite3"
CASES = [
    ("400", "rejected this seed or query"),
    ("401", "not authorized"),
    ("403", "not authorized"),
    ("429", "rate limited"),
    ("503", "unavailable"),
    ("network", "could not be reached"),
    ("timeout", "timed out"),
    ("malformed", "unsupported data"),
    ("empty", "No cultural results"),
    ("unresolved", "No cultural entity matched"),
]


def select_fault(value):
    FAULT_FILE.write_text(value)
    FAULT_FILE.chmod(0o600)


def snapshot():
    with sqlite3.connect("file:" + str(DATABASE) + "?mode=ro", uri=True) as db:
        return {row[0]: (row[1], row[2]) for row in db.execute("SELECT id,state_hash,revision FROM games")}


def budget():
    with sqlite3.connect("file:" + str(DATABASE) + "?mode=ro", uri=True) as db:
        return db.execute("SELECT sum(used) FROM qloo_daily_budget").fetchone()[0] or 0


def available():
    try:
        with httpx.Client(trust_env=False, timeout=1) as client:
            cap = client.get("http://127.0.0.1:8043/v1/capabilities").json()
            return cap.get("verification_mode") == "captured_response_replay"
    except (httpx.HTTPError, ValueError):
        return False


def start_replay():
    log = PRIVATE / "controlled-replay-service.log"
    with log.open("ab") as stream:
        env = {
            **os.environ,
            "IS_CAPTURE_REPLAY_ONLY": "1",
            "IS_CAPTURE_REPLAY_FAULT_FILE": str(FAULT_FILE),
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
                "8043",
                "--no-access-log",
            ],
            cwd=ROOT,
            env=env,
            stdout=stream,
            stderr=stream,
            start_new_session=True,
        )
    log.chmod(0o600)
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError("Owned local replay service failed to start")
        if available():
            return process
        time.sleep(0.1)
    process.terminate()
    process.wait(timeout=10)
    raise RuntimeError("Replay service startup timeout")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replace-replay-pid", required=True, type=int)
    args = parser.parse_args()
    command = subprocess.check_output(["ps", "-p", str(args.replace_replay_pid), "-o", "command="], text=True)
    if (
        "uvicorn scripts.local_cultural_verification:create_verification_app" not in command
        or "--port 8043" not in command
    ):
        raise RuntimeError("Refusing to replace any process except the verified loopback replay service")
    if not available():
        raise RuntimeError("Backend is not explicitly captured-response replay")
    browser = Safari()
    browser.load("outages")
    browser.click("resume")
    browser.wait(lambda: (v := browser.view()) and not v["title"] and not v["busy"], "saved ending")
    original = browser.idle()
    assert original["ending"] == "together"
    all_before = snapshot()
    select_fault("")
    os.kill(args.replace_replay_pid, signal.SIGTERM)
    for _ in range(100):
        if not available():
            break
        time.sleep(0.1)
    process = start_replay()
    result = {
        "kind": "safari_webdriver_controlled_replay_upstream_and_real_application_recovery",
        "new_live_qloo_requests": 0,
        "new_openai_requests": 0,
        "cases": [],
        "preserved_original_session_database": True,
    }
    try:
        # This browser resume follows an actual backend process replacement.
        resumed = browser.refresh_resume()
        assert resumed["revision"] == original["revision"] and resumed["objectives"] == original["objectives"]
        result["backend_restart_resume"] = "PASS"
        for case, message in CASES:
            entry = {"scenario": case, "status": "FAIL"}
            result["cases"].append(entry)
            try:
                browser.click("title")
                browser.wait(lambda: browser.view()["title"], "title")
                browser.add_seed("artist")
                prior_budget = budget()
                prior = snapshot()
                select_fault(case)
                browser.click("cultural")
                browser.wait(
                    lambda: message in browser.evaluate("document.querySelector('#status').textContent"),
                    "safe upstream error",
                )
                browser.wait(
                    lambda: (v := browser.view()) and not v["busy"] and not v["pending"], "terminal error settled"
                )
                time.sleep(0.4)
                expected = 1 if case == "unresolved" else 2
                assert budget() == prior_budget + expected
                assert snapshot() == prior
                select_fault("")
                after = browser.refresh_resume()
                assert (
                    after["ending"] == original["ending"]
                    and after["revision"] == original["revision"]
                    and after["objectives"] == original["objectives"]
                )
                assert budget() == prior_budget + expected
                entry.update(
                    status="PASS",
                    mock_transport_requests=expected,
                    checks=[
                        "safe replay-labelled error",
                        "no automatic provider retry or partial world",
                        "confirmed state hashes/revisions unchanged",
                        "browser refresh/resume restores exact completed quest",
                    ],
                )
            except Exception as error:
                entry["error"] = str(error)[:700]
                select_fault("")
                raise
            finally:
                print(json.dumps(entry), flush=True)
        # Healthy again: an explicit new creation succeeds without changing old worlds.
        browser.click("title")
        browser.wait(lambda: browser.view()["title"], "recovery title")
        browser.add_seed("artist")
        browser.click("cultural")
        browser.wait(lambda: (v := browser.view()) and not v["title"] and not v["busy"], "healthy generation")
        recovered = browser.idle()
        assert recovered["revision"] == 0 and len([t for t in recovered["objectives"] if "cultural memory" in t]) == 1
        assert all(snapshot().get(key) == value for key, value in all_before.items())
        result["provider_recovery"] = "PASS"
        for scenario in ("application_connection_failure", "malformed_application"):
            entry = {"scenario": scenario, "status": "FAIL"}
            result["cases"].append(entry)
            browser.load(scenario)
            browser.click("resume")
            browser.wait(lambda: (v := browser.view()) and not v["title"] and not v["busy"], "active save")
            browser.click("title")
            browser.wait(lambda: browser.view()["title"], "transport title")
            browser.add_seed("artist")
            prior = snapshot()
            count = budget()
            if scenario == "application_connection_failure":
                process.terminate()
                process.wait(timeout=10)
                process = None
            else:
                select_fault(scenario)
            browser.click("cultural")
            browser.wait(
                lambda: (v := browser.view()) and v["pending"] and not v["busy"], "uncertain request retained", 80
            )
            assert snapshot() == prior and budget() == count
            select_fault("")
            if process is None:
                process = start_replay()
            after = browser.refresh_resume()
            assert after["revision"] == 0 and len([t for t in after["objectives"] if "cultural memory" in t]) == 1
            now = snapshot()
            assert len(now) == len(prior) + 1 and budget() == count + 2
            assert all(now.get(key) == value for key, value in prior.items())
            browser.click("retry")
            browser.wait(
                lambda: "no pending request" in browser.evaluate("document.querySelector('#status').textContent"),
                "no duplicate retry",
            )
            assert snapshot() == now and budget() == count + 2
            entry.update(
                status="PASS",
                checks=[
                    "uncertain request retained without partial world",
                    "refresh/Resume completes one pending creation",
                    "one new world and cultural objective; prior state hashes unchanged",
                    "Retry after confirmation does not repeat provider or state change",
                ],
            )
            print(json.dumps(entry), flush=True)
        result["status"] = "PASS"
    except Exception as error:
        result.update(status="FAIL", error=str(error)[:700])
    finally:
        select_fault("")
        if process is None:
            process = start_replay()
        result["replay_service_healthy_after_test"] = available()
        result["owned_replay_pid"] = process.pid
        (ROOT / "reports/SAFARI_FAILURE_ACCEPTANCE_20261020.json").write_text(json.dumps(result, indent=2) + "\n")
        browser.http.close()
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
