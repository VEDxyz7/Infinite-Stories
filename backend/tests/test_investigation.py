"""Offline investigation rules with actual captured cultural fields, not live Qloo."""

import secrets
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.content import make_chapter, validate_chapter
from backend.app.culture import chapter_for_state
from backend.app.engine import apply_command, game_view
from backend.app.main import create_app
from backend.app.models import Command, DomainError, GameState
from backend.app.understanding import witness
from backend.tests.test_cultural_production import harness
from backend.tests.test_service import action, choose, move


@pytest.fixture
def saved(tmp_path):
    config, provider, calls, interest, _ = harness(tmp_path, "artist")
    with TestClient(create_app(config, cultural_provider=provider)) as client:
        headers = {"Authorization": "Bearer " + secrets.token_urlsafe(32)}
        response = client.post(
            "/v1/sessions",
            headers=headers,
            json={"request_id": str(uuid4()), "mode": "cultural", "interests": [interest]},
        )
        assert response.status_code == 200
        assert len(calls) == 2  # MockTransport only.
        yield client, headers, response.json()


def test_legacy_context_keeps_geometry_prerequisites_and_no_new_proofs(saved):
    _, _, view = saved
    state = GameState.model_validate(view["state"])
    state.city_generation = None  # Explicitly construct a legacy save without a procedural plan.
    state.cultural_context.rule_version = "cultural-cards-v1"
    base = make_chapter()
    snapshot = base.model_dump()
    old = chapter_for_state(base, state)
    assert [p.rows for p in old.locations] == [p.rows for p in base.locations]
    assert not any(o.id.startswith("screening_note") for p in old.locations for o in p.objects)
    ivo = next(o for p in old.locations for o in p.objects if o.id == "ivo")
    assert ivo.choices[0].requires == ["map"]
    assert all(not c.id.startswith("prove_") for p in old.locations for o in p.objects for c in o.choices)
    assert base.model_dump() == snapshot


def test_five_link_campaign_is_reachable_and_all_proofs_required(saved):
    _, _, view = saved
    state = GameState.model_validate(view["state"])
    state.city_generation = None  # Legacy v3 layout stress; procedural five-link coverage is separate.
    # Repeat an actual captured link solely to stress the maximum campaign size.
    # This is not a claim that the provider accepts duplicate interests.
    link = state.cultural_context.links[0]
    state.cultural_context.links = [link.model_copy(deep=True) for _ in range(5)]
    state.flags = ["map"]
    state.location_id = "market"
    base = make_chapter()
    for i in range(5):
        chapter = chapter_for_state(base, state)
        validate_chapter(chapter)
        note = next(o for p in chapter.locations for o in p.objects if o.id == f"screening_note_{i}")
        state.x, state.y = note.x, note.y
        state, _ = apply_command(base, state, Command(kind="choose", target=note.id, choice=note.choices[0].id))
    state.x, state.y = 14, 9
    state, _ = apply_command(
        base,
        state,
        Command(kind="choose", target="ivo", choice="learn_rhythm"),
        understanding=witness(state, "ivo", "learn_rhythm"),
    )
    state.location_id = "archive"
    for i in range(5):
        card = next(
            o for p in chapter_for_state(base, state).locations for o in p.objects if o.id == f"cultural_echo_{i}"
        )
        state.x, state.y = card.x, card.y
        state, _ = apply_command(base, state, Command(kind="choose", target=card.id, choice=card.choices[0].id))
    state.x, state.y = 14, 9
    state, _ = apply_command(
        base,
        state,
        Command(kind="choose", target="sera", choice="promise_guard"),
        understanding=witness(state, "sera", "promise_guard"),
    )
    state.location_id = "station"
    for i in range(5):
        with pytest.raises(DomainError) as blocked:
            apply_command(base, state, Command(kind="choose", target="beacon", choice="light_together"))
        assert blocked.value.code == "PREREQUISITE_MISSING"
        visible = game_view(base, state, "offline", 0)["nearby"]
        choices = next(o["choices"] for o in visible if o["id"] == "beacon")
        assert len(choices) == 2
        proof = next(c for c in choices if c["id"].startswith(f"prove_{i}_"))
        state, _ = apply_command(
            base,
            state,
            Command(kind="choose", target="beacon", choice=proof["id"]),
            understanding=witness(state, "beacon", proof["id"]),
        )
    state, _ = apply_command(base, state, Command(kind="choose", target="beacon", choice="leave_keeper"))
    assert state.ending == "keeper"
    assert state.visits == 3  # Direct choices enter Ivo, Sera and the Curator; setup injected the map.
    assert all(f"proof_{i}" in state.flags and f"trace_{i}" in state.flags for i in range(5))


def test_false_claims_and_early_rhythm_leave_saved_state_unchanged(saved):
    client, headers, view = saved
    view = choose(client, headers, view, "mara", "take_map")
    from backend.tests.test_service import visit_next

    view = move(client, headers, visit_next(client, headers, view), 14, 9)
    early = action(client, headers, view, {"kind": "choose", "target": "ivo", "choice": "learn_rhythm"})
    assert early.status_code == 409 and early.json()["error"]["code"] == "PREREQUISITE_MISSING"
    from backend.tests.test_service import goto_object

    view = goto_object(client, headers, view, "screening_note_0")
    before = view["state"]
    false = action(
        client, headers, view, {"kind": "choose", "target": "screening_note_0", "choice": "hypothesis_screen_0"}
    )
    assert false.status_code == 409 and false.json()["error"]["code"] == "EVIDENCE_UNSUPPORTED"
    loaded = client.get("/v1/sessions/" + view["session_id"], headers=headers).json()
    assert loaded["state"] == before and loaded["revision"] == view["revision"]
    choice = next(o for o in loaded["nearby"] if o["id"] == "screening_note_0")["choices"][0]["id"]
    request_id = str(uuid4())
    body = {"kind": "choose", "target": "screening_note_0", "choice": choice}
    accepted = action(client, headers, view, body, request_id)
    assert accepted.status_code == 200
    replay = action(client, headers, view, body, request_id)
    assert replay.status_code == 200 and replay.json()["idempotent_replay"]
    assert replay.json()["state"] == accepted.json()["state"]
    assert replay.json()["revision"] == view["revision"] + 1
    assert replay.json()["state"]["visits"] == view["state"]["visits"]


def test_empty_provider_result_cannot_replace_investigation_progress_and_restart_recovers(tmp_path):
    from dataclasses import replace

    import httpx

    from backend.tests.test_cultural_production import captured, envelope

    _, search, recs, _ = captured("artist")
    failed = False

    def upstream(request):
        if request.url.path == "/search":
            return httpx.Response(200, json=envelope(search))
        return httpx.Response(200, json={"success": True, "results": {"entities": []}} if failed else envelope(recs))

    config, provider, calls, interest, _ = harness(tmp_path, "artist", upstream, qloo_cache_seconds=0)
    headers = {"Authorization": "Bearer " + secrets.token_urlsafe(32)}
    with TestClient(create_app(config, cultural_provider=provider)) as client:
        body = {"request_id": str(uuid4()), "mode": "cultural", "interests": [interest]}
        result = client.post("/v1/sessions", headers=headers, json=body)
        assert result.status_code == 200
        view = choose(client, headers, result.json(), "mara", "take_map")
        from backend.tests.test_service import goto_object

        view = goto_object(client, headers, view, "screening_note_0")
        note = next(o for o in view["nearby"] if o["id"] == "screening_note_0")
        traced = action(
            client, headers, view, {"kind": "choose", "target": note["id"], "choice": note["choices"][0]["id"]}
        )
        assert traced.status_code == 200
        saved = traced.json()
        failed = True
        new_body = {**body, "request_id": str(uuid4())}
        rejected = client.post("/v1/sessions", headers=headers, json=new_body)
        assert rejected.status_code == 422 and rejected.json()["error"]["code"] == "QLOO_EMPTY"
        assert len(calls) == 4
        repeated = client.post("/v1/sessions", headers=headers, json=new_body)
        assert repeated.status_code == 422 and len(calls) == 4
    with TestClient(create_app(replace(config, qloo_calls_allowed=False, qloo_key=""))) as restarted:
        restored = restarted.get("/v1/sessions/" + saved["session_id"], headers=headers).json()
        assert restored["state"] == saved["state"] and restored["revision"] == saved["revision"]
        assert {"map", "trace_0"} <= set(restored["state"]["flags"])
    failed = False
    with TestClient(create_app(config, cultural_provider=provider)) as recovered:
        fresh = recovered.post("/v1/sessions", headers=headers, json={**body, "request_id": str(uuid4())})
        assert fresh.status_code == 200 and len(calls) == 6
        restored = recovered.get("/v1/sessions/" + saved["session_id"], headers=headers).json()
        assert restored["state"] == saved["state"]
