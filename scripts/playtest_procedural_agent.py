"""Opt-in two isolated actual-local-model campaigns; Qloo is captured MockTransport.

Movement/interact inputs are driven by the saved map, like player controls. Every
clue grant, commitment, proof and ending goes through the actual GM /turns path.
No solver witness/canned model response is supplied by this playtest.
"""

import argparse
import copy
import json
import secrets
import statistics
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.culture import chapter_for_state
from backend.app.local_game_master import OllamaGameMaster
from backend.app.main import create_app
from backend.app.models import CulturalEvidenceReply, GameState
from backend.tests.test_cultural_production import harness
from backend.tests.test_service import action, goto_object


def campaign(category, output, model):
    output.mkdir()
    report = {
        "category": category,
        "kind": "actual_local_model_backend_campaign",
        "Qloo_mode": "historical_captured_evidence",
        "turns": [],
        "checks": [],
        "pass": False,
    }

    def save():
        (output / "report.json").write_text(json.dumps(report, indent=2))

    with tempfile.TemporaryDirectory(prefix="infinite-agent-city-") as folder:
        config, provider, qloo_calls, interest, _ = harness(Path(folder), category)
        config = replace(config, llm_provider="ollama", llm_model=model, llm_calls_allowed=True)
        gm = OllamaGameMaster(config)
        run_model = gm.run

        async def recorded(chapter, view, text):
            before = time.perf_counter()
            row = {
                "input": text,
                "before": {
                    "location": view["state"]["location_id"],
                    "revision": view["revision"],
                    "flags": view["state"]["flags"],
                    "choices": view["state"]["choices"],
                    "visits": view["state"]["visits"],
                },
            }
            report["turns"].append(row)
            try:
                reply = await run_model(chapter, view, text)
                command, narrative = reply
                row.update(proposal=command.model_dump(mode="json") if command else None, narrative=narrative)
                if isinstance(reply, CulturalEvidenceReply):
                    row.update(
                        observations=[o.model_dump(mode="json") for o in reply.observations],
                        understanding=reply.understanding,
                        source=reply.source,
                    )
                return reply
            except Exception as error:
                row["error"] = getattr(error, "code", type(error).__name__)
                raise
            finally:
                row.update(wall_ms=round((time.perf_counter() - before) * 1000), metrics=copy.deepcopy(gm.metrics))
                save()

        gm.run = recorded
        headers = {"Authorization": "Bearer " + secrets.token_urlsafe(32)}
        final_view = None
        try:
            with TestClient(create_app(config, game_master=gm, cultural_provider=provider)) as client:
                body = {"request_id": str(uuid4()), "mode": "cultural", "interests": [interest]}
                created = client.post("/v1/sessions", headers=headers, json=body)
                assert created.status_code == 200, created.text
                view = created.json()
                url = "/v1/sessions/" + view["session_id"]
                plan = copy.deepcopy(view["state"]["city_generation"])
                report.update(
                    favourite=interest["name"],
                    seed=plan["seed"],
                    plan=plan,
                    initial_context=view["state"]["cultural_context"],
                    session_id=view["session_id"],
                )
                assert len(qloo_calls) == 2
                creation_replay = client.post("/v1/sessions", headers=headers, json=body)
                assert (
                    creation_replay.status_code == 200
                    and creation_replay.json()["session_id"] == view["session_id"]
                    and len(qloo_calls) == 2
                )
                report["checks"].append("creation receipt replay: same run and captured operations")

                def turn(text, required_flag=None, expected_tool=None, readonly=False, replay=False):
                    nonlocal view
                    if len(report["turns"]) >= 14:
                        raise AssertionError("Bounded campaign turn limit14")
                    before = copy.deepcopy(view)
                    request = {"request_id": str(uuid4()), "expected_revision": view["revision"], "text": text}
                    response = client.post(url + "/turns", headers=headers, json=request)
                    report["turns"][-1]["http_status"] = response.status_code
                    if response.status_code != 200:
                        report["turns"][-1]["api_error"] = response.json().get("error", {})
                        save()
                    assert response.status_code == 200, response.text
                    view = response.json()
                    report["turns"][-1]["after"] = {
                        "revision": view["revision"],
                        "flags": view["state"]["flags"],
                        "choices": view["state"]["choices"],
                        "visits": view["state"]["visits"],
                        "ending": view["state"]["ending"],
                    }
                    assert view["state"]["city_generation"] == plan
                    if required_flag:
                        assert required_flag in view["state"]["flags"], "MISSING_PROGRESS:" + required_flag
                    if expected_tool:
                        assert any(o["tool_id"] == expected_tool for o in view.get("tool_results", [])), (
                            "TOOL_NOT_USED:" + expected_tool
                        )
                    if readonly:
                        for key in ["flags", "choices", "visits", "ending", "understanding_records"]:
                            assert view["state"][key] == before["state"][key], "READ_CHANGED:" + key
                    if replay:
                        count = len(report["turns"])
                        again = client.post(url + "/turns", headers=headers, json=request)
                        assert (
                            again.status_code == 200
                            and again.json()["idempotent_replay"]
                            and again.json()["state"] == view["state"]
                            and len(report["turns"]) == count
                        )
                        report["checks"].append("action receipt replay: exact state, no repeated inference")
                    report["turns"][-1]["verified"] = True
                    save()
                    return view

                def arrive(resident):
                    nonlocal view
                    view = goto_object(client, headers, view, resident)
                    response = action(client, headers, view, {"kind": "interact", "target": resident})
                    assert response.status_code == 200, response.text
                    view = response.json()

                def explanation(resident):
                    from backend.app.understanding import topic

                    t = topic(GameState.model_validate(view["state"]), resident)
                    return f"The saved catalogue returns {t['target']['name']} for {t['source']['name']}. This indicates aggregate cultural affinity, not proof they collaborated or evidence about my personality. Our city setting is creative fiction, not a provider fact."

                seed = view["state"]["cultural_context"]["links"][0]["seed"]
                selected = next(
                    e
                    for e in view["state"]["cultural_context"]["links"][0]["recommendations"]
                    if e["entity_id"] == view["state"]["cultural_context"]["links"][0]["selected_id"]
                )
                turn(
                    "Search the saved catalogue for " + seed["name"] + ".",
                    expected_tool="search_entities",
                    readonly=True,
                )
                turn(
                    "List the saved recommendations for " + seed["name"] + ".",
                    expected_tool="get_related_entities",
                    readonly=True,
                )
                turn(
                    "What does the saved connection from "
                    + seed["name"]
                    + " to "
                    + selected["name"]
                    + " actually establish?",
                    expected_tool="inspect_connection",
                    readonly=True,
                )
                arrive("mara")
                turn("Describe the record bar atmosphere briefly. I am not accepting any offer yet.", readonly=True)
                turn(explanation("mara") + " Please entrust me with your map.", "map", replay=True)
                for index in plan["proof_order"]:
                    target = "screening_note_" + str(index)
                    view = goto_object(client, headers, view, target)
                    obj = next(o for o in view["nearby"] if o["id"] == target)
                    turn(next(c["label"] for c in obj["choices"] if c["grants"]), "trace_" + str(index))
                arrive("ivo")
                turn(explanation("ivo") + " Please teach me the rhythm.", "rhythm")
                for index in plan["proof_order"]:
                    target = "cultural_echo_" + str(index)
                    view = goto_object(client, headers, view, target)
                    obj = next(o for o in view["nearby"] if o["id"] == target)
                    turn(next(c["label"] for c in obj["choices"] if c["grants"]), "culture_" + str(index))
                arrive("sera")
                turn(explanation("sera") + " I choose to guard the private letters.", "chronicle")
                assert "guarding" in view["state"]["flags"] and "sharing" not in view["state"]["flags"]
                arrive("beacon")
                invalid = action(
                    client, headers, view, {"kind": "choose", "target": "beacon", "choice": "light_together"}
                )
                assert invalid.status_code == 409
                unchanged = client.get(url, headers=headers).json()
                assert unchanged["state"] == view["state"] and unchanged["revision"] == view["revision"]
                report["checks"].append("early escape rejected by engine before confirmed proof")
                for index in plan["proof_order"]:
                    turn(explanation("beacon") + " I present this connection as my proof.", "proof_" + str(index))
                turn("I light the beacon and leave together with my friends.", "beacon")
                assert view["state"]["ending"] == "together" and view["state"]["visits"] == 4
                assert len(view["state"]["understanding_records"]) == 4
                assert view["state"]["city_generation"] == plan and len(qloo_calls) == 2
                assert (
                    client.get(url, headers={"Authorization": "Bearer " + secrets.token_urlsafe(32)}).status_code == 404
                )
                saved = client.get(url, headers=headers).json()
                assert saved["state"] == view["state"]
                report["checks"].append("refresh GET: exact confirmed state and seed; foreign owner rejected")
                final_view = saved
                # Current Taste Card is rendered in GameUI.ShowEnding, not a backend endpoint.
                report["taste_card_inputs"] = {
                    "ending": saved["state"]["ending"],
                    "visits": saved["state"]["visits"],
                    "flags": saved["state"]["flags"],
                    "last_history": saved["state"]["history"][-1],
                    "saved_pair": [seed["name"], selected["name"]],
                }
                (output / "ending-view.json").write_text(json.dumps(saved, indent=2))
                saved_shape = chapter_for_state(
                    client.app.state.store.chapter, GameState.model_validate(saved["state"])
                ).model_dump(mode="json")
            with TestClient(
                create_app(replace(config, qloo_calls_allowed=False, qloo_key="", llm_calls_allowed=False))
            ) as fresh:
                resumed = fresh.get(url, headers=headers)
                assert (
                    resumed.status_code == 200
                    and resumed.json()["state"] == final_view["state"]
                    and resumed.json()["revision"] == final_view["revision"]
                )
                actual = chapter_for_state(
                    fresh.app.state.store.chapter, GameState.model_validate(resumed.json()["state"])
                ).model_dump(mode="json")
                assert actual == saved_shape
            report["checks"].append(
                "fresh app with both providers disabled resumes exact seed, world, outcomes and revision"
            )
            from backend.app.city_generation import generate

            state = GameState.model_validate(final_view["state"])
            regenerated_context, regenerated_plan = generate(
                state.cultural_context, state.city_generation.candidate, state.city_generation.seed
            )
            assert regenerated_plan == state.city_generation and regenerated_context == state.cultural_context
            assert len(state.choices) == len(set(state.choices)) == 7
            assert {record.resident for record in state.understanding_records} == {"mara", "ivo", "sera", "beacon"}
            report["checks"].append(
                "saved inputs and seed reproduce exact plan/context; unique confirmed choices and residents"
            )
            report.update(
                {
                    "pass": True,
                    "ending": final_view["state"]["ending"],
                    "visits": final_view["state"]["visits"],
                    "final_state": final_view["state"],
                    "revision": final_view["revision"],
                }
            )
        except Exception as error:
            report.update(error=str(error)[:1800], error_type=type(error).__name__)
        finally:
            elapsed = [r["wall_ms"] for r in report["turns"]]
            report.update(
                logical_model_turns=len(elapsed),
                local_inference_requests=sum(r["metrics"].get("inference_requests", 0) for r in report["turns"]),
                median_ms=statistics.median(elapsed) if elapsed else None,
                max_ms=max(elapsed) if elapsed else None,
                total_model_turn_ms=sum(elapsed),
                live_Qloo_requests=0,
                hosted_model_requests=0,
                captured_transport_operations=len(qloo_calls),
                completed_local_inference_responses=sum(
                    len(row["metrics"].get("steps", [])) for row in report["turns"]
                ),
            )
            save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--model", default="qwen3.5:4b")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit("Requires --execute; actual local inference only")
    args.output.mkdir(exist_ok=False, parents=True)
    reports = []
    for category in ("artist", "movie"):
        report = campaign(category, args.output / category, args.model)
        reports.append(report)
        print(category, "PASS" if report["pass"] else "FAIL", report.get("error", ""), flush=True)
    (args.output / "summary.json").write_text(
        json.dumps(
            [
                {
                    k: r.get(k)
                    for k in (
                        "category",
                        "pass",
                        "seed",
                        "logical_model_turns",
                        "local_inference_requests",
                        "median_ms",
                        "max_ms",
                        "error",
                    )
                }
                for r in reports
            ],
            indent=2,
        )
    )
    if not all(r["pass"] for r in reports):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
