"""Real Safari WebDriver acceptance of the existing Unity replay build. No live providers."""

import base64
import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "reports/local/safari-acceptance"
REPORT = ROOT / "reports/SAFARI_ACCEPTANCE_20261020.json"
SEEDS = {
    "artist": "David Bowie",
    "movie": "Spirited Away",
    "brand": "LEGO",
    "videogame": "The Legend of Zelda: Breath of the Wild",
}


class Safari:
    def __init__(self):
        self.http = httpx.Client(base_url="http://127.0.0.1:4445", trust_env=False, timeout=100)
        self.session = (PRIVATE / "webdriver-session").read_text().strip()

    def call(self, method, path, data=None):
        response = self.http.request(method, "/session/" + self.session + path, json=data)
        value = response.json().get("value")
        if isinstance(value, dict) and value.get("error"):
            raise RuntimeError(value["error"] + ": " + value.get("message", "")[:500])
        response.raise_for_status()
        return value

    def evaluate(self, expression):
        return self.call("POST", "/execute/sync", {"script": "return (" + expression + ");", "args": []})

    def view(self):
        return self.evaluate('typeof current!=="undefined"&&current?JSON.parse(JSON.stringify(current)):null')

    def wait(self, predicate, label, seconds=25):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            result = predicate()
            if result:
                return result
            time.sleep(0.1)
        raise RuntimeError("Timeout: " + label)

    def click(self, command):
        return self.wait(
            lambda: self.evaluate(
                "(()=>{const b=Array.from(document.querySelectorAll('button[data-command]')).find(b=>b.dataset.command==="
                + json.dumps(command)
                + ");if(!b||b.disabled)return false;b.click();return true})()"
            ),
            "enabled " + command,
        )

    def idle(self):
        def confirmed():
            view = self.view()
            return view if view and not view["busy"] and not view["pending"] else None

        return self.wait(confirmed, "confirmed state")

    def load(self, category):
        self.call("POST", "/url", {"url": "http://127.0.0.1:8081/?safari=" + category + "&run=" + str(time.time_ns())})
        self.wait(
            lambda: self.evaluate(
                'typeof player!=="undefined"&&!!player&&typeof current!=="undefined"&&!!current&&current.cultural_available'
            ),
            "Unity ready",
            90,
        )
        assert "LOCAL CAPTURE REPLAY" in self.evaluate("document.querySelector('#status').textContent")

    def add_seed(self, category):
        self.evaluate(
            "(()=>{document.querySelector('#culture-seed').value="
            + json.dumps(SEEDS[category])
            + ";document.querySelector('#culture-category').value="
            + json.dumps(category)
            + ";document.querySelector('#culture-form').requestSubmit();return true})()"
        )

    def move(self, x, y):
        for axis, target in [("y", 8), ("x", x), ("y", y)]:
            for _ in range(40):
                view = self.idle()
                delta = target - view[axis]
                if abs(delta) < 0.65:
                    break
                command = ("east" if delta > 0 else "west") if axis == "x" else ("north" if delta > 0 else "south")
                self.click(command)

                def moved():
                    latest = self.view()
                    return (
                        latest and not latest["busy"] and not latest["pending"] and abs(latest[axis] - view[axis]) > 0.2
                    )

                self.wait(moved, "physics/autosave " + command, 12)
            else:
                raise RuntimeError("Movement failed to converge")

    def choose(self, prefix):
        before = self.idle()
        choice = next((a for a in before["actions"] if a["command"].startswith(prefix)), None)
        assert choice, "Allowed nearby choice missing: " + prefix
        self.click(choice["command"])
        self.wait(
            lambda: (v := self.view()) and v["revision"] > before["revision"] and not v["busy"], "choice confirmation"
        )

    def refresh_resume(self):
        self.call("POST", "/refresh", {})
        self.wait(
            lambda: self.evaluate('typeof player!=="undefined"&&!!player&&typeof current!=="undefined"&&!!current'),
            "reloaded Unity",
            90,
        )
        self.click("resume")
        self.wait(lambda: (v := self.view()) and not v["title"] and not v["busy"] and not v["pending"], "resumed save")
        return self.idle()


def main():
    with httpx.Client(trust_env=False) as local:
        cap = local.get("http://127.0.0.1:8043/v1/capabilities").json()
    assert cap["verification_mode"] == "captured_response_replay" and not cap["game_master_configured"]
    browser = Safari()
    report = {
        "kind": "real_safari_webdriver_unity_captured_response_replay",
        "browser": "Safari26.2 (21623.1.14.11.9)",
        "new_live_qloo_requests": 0,
        "new_openai_requests": 0,
        "journeys": [],
    }
    for category in SEEDS:
        entry = {"category": category, "seed": SEEDS[category], "status": "FAIL", "checks": []}
        report["journeys"].append(entry)
        try:
            browser.load(category)
            browser.add_seed(category)
            browser.click("cultural")
            browser.wait(
                lambda: (
                    (v := browser.view())
                    and (not v["title"] or any(a["command"].startswith("confirm:") for a in v["actions"]))
                ),
                "resolution",
            )
            view = browser.view()
            if view["title"]:
                actual = next(a for a in view["actions"] if "The Lego Group" in a["label"])
                browser.click(actual["command"])
                entry["checks"].append("confirmed actual canonical brand candidate")
            browser.wait(lambda: (v := browser.view()) and not v["title"] and not v["busy"], "created cultural world")
            view = browser.idle()
            assert any("cultural memory" in text for text in view["objectives"])
            entry["checks"].append("replay label and required cultural objective")
            revision = view["revision"]
            browser.evaluate(
                "(()=>{player.SendMessage('Infinite Stories','OnBrowserCommand','choose:cultural_echo_0:fabricated');return true})()"
            )
            time.sleep(0.25)
            assert browser.view()["revision"] == revision
            entry["checks"].append("unsupported client answer leaves revision unchanged")
            for stage in range(4):
                if stage == 2:
                    browser.move(12, 6)
                    browser.choose("choose:cultural_echo_0:")
                    entry["checks"].append("actual cultural card completed through controller/server rules")
                browser.move(14, 9)
                browser.choose(
                    [
                        "choose:mara:take_map",
                        "choose:ivo:learn_rhythm",
                        "choose:sera:promise_guard",
                        "choose:beacon:light_together",
                    ][stage]
                )
                if stage < 3:
                    browser.move(29, 8)
                    browser.choose("travel:")
                    browser.wait(lambda: browser.view()["visits"] == stage + 2, "area transition")
                print(json.dumps({"category": category, "stage": stage + 1}), flush=True)
            before = browser.idle()
            assert before["ending"] == "together" and before["visits"] == 4
            assert all(text.startswith("Complete:") for text in before["objectives"])
            label = browser.evaluate("document.querySelector('#status').textContent")
            assert "LOCAL CAPTURE REPLAY" in label and "Qloo discoveries:" in label
            entry["attribution"] = label
            screenshot = browser.call("GET", "/screenshot")
            (PRIVATE / ("safari-" + category + ".png")).write_bytes(base64.b64decode(screenshot))
            after = browser.refresh_resume()
            assert after["ending"] == before["ending"] and after["revision"] == before["revision"]
            assert after["objectives"] == before["objectives"]
            entry.update(status="PASS", ending=after["ending"], revision=after["revision"], visits=after["visits"])
            entry["checks"].extend(
                ["all objectives and four-area ending completed", "refresh/resume preserves exact revision and goals"]
            )
        except Exception as error:
            entry["error"] = str(error)[:700]
            try:
                entry["last_public_view"] = browser.view()
            except Exception:
                pass
        REPORT.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"category": category, "status": entry["status"], "error": entry.get("error")}), flush=True)
        if entry.get("error", "").startswith(("session not created", "invalid session id", "invalid session")):
            break
    browser.http.close()
    if len(report["journeys"]) != 4 or any(j["status"] != "PASS" for j in report["journeys"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
