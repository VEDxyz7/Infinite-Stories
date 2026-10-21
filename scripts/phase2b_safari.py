"""Fresh real Safari presentation acceptance; Qloo replay and bounded local inference."""

import base64
import json
import time
from pathlib import Path

import httpx

from scripts.safari_replay_acceptance import Safari

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "reports/local/phase2b"


class PhaseSafari(Safari):
    def __init__(self):
        self.http = httpx.Client(base_url="http://127.0.0.1:4446", trust_env=False, timeout=100)
        self.session = (PRIVATE / "safari-session").read_text().strip()

    def capture(self, name):
        time.sleep(0.5)
        (PRIVATE / ("safari-" + name + ".png")).write_bytes(base64.b64decode(self.call("GET", "/screenshot")))

    def ready(self):
        self.wait(
            lambda: self.evaluate('typeof player!=="undefined"&&!!player&&typeof current!=="undefined"&&!!current'),
            "Unity ready",
            90,
        )
        time.sleep(0.7)

    def physical_key(self, key, duration=200):
        self.call(
            "POST",
            "/actions",
            {
                "actions": [
                    {
                        "type": "key",
                        "id": "keyboard",
                        "actions": [
                            {"type": "keyDown", "value": key},
                            {"type": "pause", "duration": duration},
                            {"type": "keyUp", "value": key},
                        ],
                    }
                ]
            },
        )
        self.call("DELETE", "/actions")

    def physical_click(self, selector):
        point = self.evaluate(
            "(()=>{const r=document.querySelector("
            + json.dumps(selector)
            + ").getBoundingClientRect();return {x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)}})()"
        )
        self.call(
            "POST",
            "/actions",
            {
                "actions": [
                    {
                        "type": "pointer",
                        "id": "mouse",
                        "parameters": {"pointerType": "mouse"},
                        "actions": [
                            {
                                "type": "pointerMove",
                                "duration": 0,
                                "x": point["x"],
                                "y": point["y"],
                                "origin": "viewport",
                            },
                            {"type": "pointerDown", "button": 0},
                            {"type": "pointerUp", "button": 0},
                        ],
                    }
                ]
            },
        )
        self.call("DELETE", "/actions")


def main():
    b = PhaseSafari()
    report = {
        "browser": "Safari26.2 (21623.1.14.11.9)",
        "status": "FAIL",
        "qloo_mode": "historical captured-response replay",
        "model_mode": "actual local Ollama qwen3.5:4b",
        "new_live_qloo_requests": 0,
        "hosted_model_requests": 0,
        "checks": [],
    }
    upstream = PRIVATE / "backend/upstream-scenario"
    try:
        with httpx.Client(trust_env=False) as local:
            cap = local.get("http://127.0.0.1:8046/v1/capabilities").json()
        assert cap["verification_mode"] == "captured_response_replay" and cap["game_master_configured"]
        b.call("POST", "/window/rect", {"width": 1280, "height": 1000})
        b.call("POST", "/url", {"url": "http://127.0.0.1:8083/?phase2b=safari"})
        b.ready()
        b.capture("opening")
        b.physical_click("#access-toggle")
        b.add_seed("artist")
        b.click("cultural")
        b.wait(lambda: (v := b.view()) and not v["title"] and not v["busy"], "cultural world")
        assert "LOCAL CAPTURE REPLAY" in b.evaluate("document.querySelector('#status').textContent")
        report["checks"].append("title, actual mouse controls and explicit replay cultural start")
        before = b.idle()
        b.evaluate(
            "(()=>{document.querySelector('#agent-text').value='Show the saved cultural seed and recommendation names without changing progress.';document.querySelector('#agent-form').requestSubmit();return true})()"
        )
        b.wait(
            lambda: (
                (v := b.view()) and not v["busy"] and v["story"].startswith("Saved Qloo evidence (server-rendered):")
            ),
            "actual local model evidence turn",
            90,
        )
        assert b.idle()["revision"] == before["revision"]
        with httpx.Client(trust_env=False) as local:
            report["local_model_inference_requests"] = local.get(
                "http://127.0.0.1:8046/verification/local-ai/adapter"
            ).json()["latest_turn_inference_requests"]
        report["checks"].append(
            "actual local model selects read-only evidence tool; server attribution and revision preserved"
        )
        b.physical_click("#unity-canvas")
        before = b.idle()
        b.physical_key("\ue014", 220)
        b.wait(
            lambda: (v := b.view()) and not v["busy"] and abs(v["x"] - before["x"]) > 0.2,
            "physical arrow movement/autosave",
        )
        report["checks"].append("physical W3C mouse focus and right-arrow movement with autosave")
        b.click("sound")
        b.click("sound")
        b.capture("record-bar")
        b.click("scanner")
        b.wait(lambda: b.view()["panel"] == "scanner", "Scanner")
        assert "David Bowie" in b.view()["panel_text"]
        b.capture("scanner")
        rev = b.idle()["revision"]
        b.click("compare")
        b.wait(lambda: "AUTHORED CONTROL" in b.view()["panel_text"], "honest authored comparison")
        assert b.idle()["revision"] == rev
        b.capture("authored-control")
        b.call("POST", "/window/rect", {"width": 820, "height": 1000})
        b.evaluate('window.dispatchEvent(new Event("resize"))')
        assert not b.evaluate("document.documentElement.scrollWidth>innerWidth+1")
        b.capture("scanner-narrow")
        b.call("POST", "/window/rect", {"width": 1280, "height": 1000})
        b.click("continue")
        b.click("journal")
        b.wait(lambda: b.view()["panel"] == "journal", "Journal")
        assert "CONFIRMED OBJECTIVES" in b.view()["panel_text"]
        b.capture("journal")
        b.click("continue")
        report["checks"].append(
            "Scanner, honest Qloo-off control, journal, sound toggle and narrow layout without horizontal overflow"
        )
        rev = b.idle()["revision"]
        b.evaluate("player.SendMessage('Infinite Stories','OnBrowserCommand','choose:cultural_echo_0:fabricated')")
        time.sleep(0.3)
        assert b.idle()["revision"] == rev
        for stage, name in enumerate(["record-bar", "cinema", "boutique", "gate"]):
            if stage == 2:
                b.move(12, 6)
                b.choose("choose:cultural_echo_0:")
            b.move(13, 9)
            b.click("interact")
            b.wait(lambda: b.view()["panel"] == "dialogue", name + " dialogue")
            b.capture(name + "-dialogue")
            b.click("continue")
            b.choose(
                [
                    "choose:mara:take_map",
                    "choose:ivo:learn_rhythm",
                    "choose:sera:promise_guard",
                    "choose:beacon:light_together",
                ][stage]
            )
            if stage < 3:
                b.move(29, 8)
                b.choose("travel:")
                b.wait(lambda: b.view()["visits"] == stage + 2, "venue transition")
            print(json.dumps({"safari_stage": name, "status": "PASS"}), flush=True)
        ended = b.idle()
        assert ended["ending"] == "together" and ended["visits"] == 4
        assert all(t.startswith("Complete:") for t in ended["objectives"])
        b.capture("taste-card")
        resumed = b.refresh_resume()
        assert (
            resumed["revision"] == ended["revision"]
            and resumed["objectives"] == ended["objectives"]
            and resumed["ending"] == "together"
        )
        report["checks"].append(
            "four furnished venues, distinct dialogue, cultural card, valid rules, clock4/12, together ending and exact refresh/resume"
        )
        report["completed_revision"] = ended["revision"]
        b.click("title")
        b.wait(lambda: b.view()["title"], "title after save")
        b.add_seed("artist")
        upstream.write_text("503")
        try:
            b.click("cultural")
            b.wait(
                lambda: (
                    not b.view()["busy"]
                    and "unavailable" in b.evaluate("document.querySelector('#status').textContent").lower()
                ),
                "clear controlled provider error",
            )
            assert b.view()["title"]
            b.capture("creation-error")
        finally:
            upstream.write_text("")
        b.click("resume")
        b.wait(lambda: b.view()["ending"] == "together" and not b.view()["title"], "recover existing saved ending")
        assert b.idle()["revision"] == ended["revision"]
        b.refresh_resume()
        assert b.idle()["revision"] == ended["revision"]
        report["checks"].append(
            "controlled replay503 creation failure preserves prior ending; reset, resume and refresh recover exact save"
        )
        b.click("title")
        b.wait(lambda: b.view()["title"], "title before gentle journey")
        b.click("authored")
        b.wait(lambda: not b.view()["title"] and not b.view()["busy"], "authored journey")
        while not b.idle()["ending"]:
            v = b.idle()
            b.move(2 if v["x"] < 15 else 29, 8)
            b.choose("travel:")
        dawn = b.idle()
        assert dawn["ending"] == "dawn" and dawn["visits"] == 12
        b.capture("gentle-ending")
        resumed = b.refresh_resume()
        assert resumed["ending"] == "dawn" and resumed["revision"] == dawn["revision"]
        report["checks"].append("actual engine12-visit gentle dawn ending and refresh/resume")
        report["status"] = "PASS"
    except Exception as error:
        report["error"] = str(error)[:800]
        try:
            report["last_public_view"] = b.view()
            b.capture("failure")
        except Exception:
            pass
        raise
    finally:
        upstream.write_text("")
        (PRIVATE / "safari-final.json").write_text(json.dumps(report, indent=2) + "\n")
        b.http.close()
        print(json.dumps({"safari": report["status"], "error": report.get("error")}), flush=True)


if __name__ == "__main__":
    main()
