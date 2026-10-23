"""Offline rules/witness regressions; no network or inference."""

import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.config import Settings
from backend.app.content import make_chapter
from backend.app.engine import apply_command
from backend.app.main import create_app
from backend.app.models import Command, DomainError, GameState, TurnRequest
from backend.app.solvability import MAX_CANDIDATES, activate_candidate, solve
from backend.app.store import games, generations
from backend.tests.test_cultural_production import harness
from backend.tests.test_service import action, move, start


@pytest.fixture(params=["sqlite", "postgres"])
def setup(tmp_path, request):
    url = "sqlite:///" + str(tmp_path / "rules.sqlite3")
    if request.param == "postgres":
        if not os.getenv("IS_TEST_POSTGRES_URL"):
            pytest.skip("Requires the real disposable PostgreSQL runner")
        url = os.environ["IS_TEST_POSTGRES_URL"]
    config = Settings(database_url=url, environment="test", requests_per_minute=1000)
    with TestClient(create_app(config)) as client:
        yield client, client.app, config


def fresh(**kwargs):
    return GameState(visit_rules="conversation-v1", visits=0, x=14, y=9, **kwargs)


@pytest.mark.parametrize(
    "resident,place", [("mara", "quay"), ("ivo", "market"), ("sera", "archive"), ("beacon", "station")]
)
@pytest.mark.parametrize("kind", ["interact", "inspect"])
def test_every_conversation_entry_and_continuation(resident, place, kind):
    state = fresh(location_id=place)
    for _ in range(15):
        state, _ = apply_command(make_chapter(), state, Command(kind=kind, target=resident))
        assert state.visits == 1 and state.encounter_id == resident
    state, _ = apply_command(make_chapter(), state, Command(kind="position", x=14, y=6))
    assert state.visits == 1
    state, _ = apply_command(make_chapter(), state, Command(kind="position", x=14, y=5))
    assert state.encounter_id == ""
    state, _ = apply_command(make_chapter(), state, Command(kind="position", x=14, y=9))
    state, _ = apply_command(make_chapter(), state, Command(kind=kind, target=resident))
    assert state.visits == 2


@pytest.mark.parametrize(
    "resident,place,choice,flags",
    [
        ("mara", "quay", "take_map", []),
        ("ivo", "market", "learn_rhythm", ["map"]),
        ("sera", "archive", "promise_guard", ["rhythm"]),
        ("beacon", "station", "light_together", ["map", "rhythm", "chronicle"]),
    ],
)
def test_direct_choice_charges_encounter(resident, place, choice, flags):
    state = fresh(location_id=place, flags=flags)
    changed, _ = apply_command(make_chapter(), state, Command(kind="choose", target=resident, choice=choice))
    assert changed.visits == 1
    assert state.visits == 0


def test_twelfth_encounter_can_finish_but_leaving_ends_night():
    state = fresh()
    state.visits = 11
    state, _ = apply_command(make_chapter(), state, Command(kind="interact", target="mara"))
    assert state.visits == 12 and not state.ending
    state, _ = apply_command(make_chapter(), state, Command(kind="choose", target="mara", choice="take_map"))
    assert state.visits == 12 and state.flags == ["map"]
    state, _ = apply_command(make_chapter(), state, Command(kind="position", x=14, y=5))
    assert state.ending == "dawn" and state.visits == 12
    with pytest.raises(DomainError, match="STORY_COMPLETE"):
        apply_command(make_chapter(), state, Command(kind="interact", target="mara"))


def test_final_proof_can_win_on_visit_twelve():
    state = fresh(location_id="station", flags=["map", "rhythm", "chronicle"])
    state.visits = 11
    state, _ = apply_command(make_chapter(), state, Command(kind="choose", target="beacon", choice="light_together"))
    assert state.visits == 12 and state.ending == "together"


def test_no_thirteenth_encounter_or_invalid_charge():
    state = fresh()
    with pytest.raises(DomainError):
        apply_command(make_chapter(), state, Command(kind="choose", target="mara", choice="fabricated"))
    assert state.visits == 0
    state.visits = 12
    changed, _ = apply_command(make_chapter(), state, Command(kind="interact", target="mara"))
    assert changed.ending == "dawn" and changed.visits == 12 and not changed.flags


def test_legacy_save_keeps_travel_rules():
    state = GameState.model_validate({"x": 29, "y": 8})
    assert state.visit_rules == "travel-v1"
    state, _ = apply_command(make_chapter(), state, Command(kind="travel", target="quay_east"))
    assert state.visits == 2
    state.x, state.y = 14, 9
    state, _ = apply_command(make_chapter(), state, Command(kind="interact", target="ivo"))
    assert state.visits == 2


def test_connected_missing_gate_prerequisite_rejected():
    chapter = make_chapter()
    gate = next(o for p in chapter.locations for o in p.objects if o.id == "beacon")
    for choice in gate.choices:
        choice.requires.append("never_granted")
    with pytest.raises(DomainError) as error:
        activate_candidate(chapter, fresh())
    assert error.value.code == "CITY_UNSOLVABLE"


@pytest.mark.parametrize("category", ["artist", "movie", "brand", "videogame"])
def test_real_captured_category_witness_and_final_visit(tmp_path, category):
    config, provider, calls, interest, _ = harness(tmp_path, category)
    with TestClient(create_app(config, cultural_provider=provider)) as client:
        response, headers, _ = start_category(client, interest)
        assert response.status_code == 200, response.text
        state = GameState.model_validate(response.json()["state"])
        assert state.visits == 0 and len(calls) == 2  # MockTransport only.
        commands, final = solve(make_chapter(), state)
        assert final.ending == "together" and final.visits == 4
        assert "proof_0" in final.flags and "trace_0" in final.flags
        assert state.activation_validation.steps == len(commands)
        state.visits = 8
        _, last = solve(make_chapter(), state)
        assert last.visits == 12 and last.ending == "together"
        assert len(calls) == 2


def start_category(client, interest):
    headers = {"Authorization": "Bearer " + secrets.token_urlsafe(32)}
    body = {"request_id": str(uuid4()), "mode": "cultural", "interests": [interest]}
    return client.post("/v1/sessions", headers=headers, json=body), headers, body


def test_alternate_candidate_and_exhaustion(tmp_path, monkeypatch):
    import backend.app.solvability as solver

    _, provider, calls, interest, _ = harness(tmp_path, "artist")
    from backend.app.models import Interest

    context = provider.generate([Interest.model_validate(interest)])
    state = fresh(mode="cultural", cultural_source="qloo", cultural_context=context)
    original = solver.solve
    seen = []

    def reject_first(base, candidate):
        seen.append(str(candidate.cultural_context.links[0].selected_id))
        if len(seen) == 1:
            raise ValueError("Controlled first candidate failure")
        return original(base, candidate)

    monkeypatch.setattr(solver, "solve", reject_first)
    activated = solver.activate_candidate(make_chapter(), state)
    assert activated.activation_validation.candidate == 1 and len(seen) == 2
    assert seen[0] != seen[1] and len(calls) == 2
    seen.clear()

    def impossible(base, candidate):
        seen.append(candidate)
        raise ValueError("Controlled exhaustion")

    monkeypatch.setattr(solver, "solve", impossible)
    with pytest.raises(DomainError) as error:
        solver.activate_candidate(make_chapter(), state)
    assert error.value.code == "CITY_UNSOLVABLE" and len(seen) == MAX_CANDIDATES
    assert len(calls) == 2


def test_activation_failure_keeps_prior_save_and_terminal_receipt(tmp_path, monkeypatch):
    import backend.app.solvability as solver

    config, provider, calls, interest, _ = harness(tmp_path, "brand")
    with TestClient(create_app(config, cultural_provider=provider)) as client:
        prior, headers, _ = start_category(client, interest)
        assert prior.status_code == 200
        before = prior.json()
        monkeypatch.setattr(solver, "solve", lambda *args: (_ for _ in ()).throw(ValueError("No path")))
        body = {"request_id": str(uuid4()), "mode": "cultural", "interests": [interest]}
        for _ in range(2):
            failed = client.post("/v1/sessions", headers=headers, json=body)
            assert failed.status_code == 503 and failed.json()["error"]["code"] == "CITY_UNSOLVABLE"
        assert len(calls) == 2  # Existing private cache supplies the second generation; no new transport calls.
        loaded = client.get("/v1/sessions/" + before["session_id"], headers=headers).json()
        assert loaded["state"] == before["state"] and loaded["revision"] == 0
        with client.app.state.store.engine.connect() as connection:
            assert len(connection.execute(select(games)).all()) == 1
            assert sorted(connection.execute(select(generations.c.status)).scalars()) == ["complete", "failed"]


def test_concurrent_encounter_replay_and_restart(setup):
    client, _, config = setup
    response, headers, _ = start(client)
    view = move(client, headers, response.json(), 14, 9)
    rid = str(uuid4())
    command = {"kind": "interact", "target": "mara"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: action(client, headers, view, command, rid), range(2)))
    assert all(r.status_code == 200 for r in responses)
    assert all(r.json()["state"]["visits"] == 1 for r in responses)
    final = responses[-1].json()
    with TestClient(create_app(config)) as restarted:
        loaded = restarted.get("/v1/sessions/" + final["session_id"], headers=headers).json()
        assert loaded["state"] == final["state"] and loaded["revision"] == final["revision"]
        assert action(restarted, headers, view, command, rid).json()["state"]["visits"] == 1


def test_model_dialogue_entry_continuation_and_evidence_free(setup):
    client, app, _ = setup
    response, headers, _ = start(client)
    view = move(client, headers, response.json(), 14, 9)
    token = headers["Authorization"].removeprefix("Bearer ")
    store = app.state.store
    for source, expected in [("cultural_evidence_tool", 0), (None, 1), (None, 1)]:
        request = TurnRequest(request_id=uuid4(), expected_revision=view["revision"], text="Question")
        store.reserve_turn(view["session_id"], token, request, 20)
        view = store.finish_turn(view["session_id"], token, request, None, "Model fixture reply", source)
        assert view["state"]["visits"] == expected
        replay, pending = store.reserve_turn(view["session_id"], token, request, 20)
        assert pending is None and replay == view


def test_solver_detects_cycles_and_deadline_exhaustion():
    chapter = make_chapter()
    mara = next(o for p in chapter.locations for o in p.objects if o.id == "mara")
    mara.choices[0].requires = ["chronicle"]
    with pytest.raises(DomainError, match="CITY_UNSOLVABLE"):
        activate_candidate(chapter, fresh())
    exhausted = fresh()
    exhausted.visits = 12
    with pytest.raises(DomainError, match="CITY_UNSOLVABLE"):
        activate_candidate(make_chapter(), exhausted)


def test_maximum_campaign_has_engine_witness_without_spending_extra_visits(tmp_path):
    from backend.app.models import Interest

    _, provider, calls, interest, _ = harness(tmp_path, "artist")
    context = provider.generate([Interest.model_validate(interest)])
    context.links = [context.links[0].model_copy(deep=True) for _ in range(5)]
    state = fresh(mode="cultural", cultural_source="qloo", cultural_context=context)
    validated = activate_candidate(make_chapter(), state)
    _, final = solve(make_chapter(), validated)
    assert final.visits == 4 and final.ending == "together"
    assert all(
        f"proof_{i}" in final.flags and f"culture_{i}" in final.flags and f"trace_{i}" in final.flags for i in range(5)
    )
    assert len(calls) == 2


@pytest.mark.parametrize("damage", ["empty", "malformed", "missing_selected"])
def test_mutated_evidence_cannot_obtain_activation_certificate(tmp_path, damage):
    from pydantic import ValidationError

    from backend.app.models import Interest

    _, provider, calls, interest, _ = harness(tmp_path, "artist")
    context = provider.generate([Interest.model_validate(interest)])
    state = fresh(mode="cultural", cultural_source="qloo", cultural_context=context)
    if damage == "empty":
        state.cultural_context.links = []
    elif damage == "malformed":
        state.cultural_context.links[0].evidence[1].params["filter.type"] = "urn:entity:book"
    else:
        state.cultural_context.links[0].selected_id = uuid4()
    with pytest.raises(ValidationError):
        activate_candidate(make_chapter(), state)
    assert state.activation_validation is None and len(calls) == 2


def test_legacy_raw_save_is_not_rewritten_on_resume(setup):
    from sqlalchemy import update

    from backend.app.store import digest

    client, app, config = setup
    response, headers, _ = start(client)
    view = response.json()
    old = dict(view["state"])
    for field in ("visit_rules", "encounter_id", "activation_validation"):
        old.pop(field)
    old.update(visits=7, flags=["map"], choices=["take_map"])
    with app.state.store.engine.begin() as connection:
        connection.execute(
            update(games).where(games.c.id == view["session_id"]).values(state=old, state_hash=digest(old))
        )
    with TestClient(create_app(config)) as restarted:
        loaded = restarted.get("/v1/sessions/" + view["session_id"], headers=headers)
        assert loaded.status_code == 200
        assert loaded.json()["state"]["visit_rules"] == "travel-v1" and loaded.json()["state"]["visits"] == 7
    with app.state.store.engine.connect() as connection:
        raw = connection.execute(select(games.c.state).where(games.c.id == view["session_id"])).scalar_one()
        assert raw == old


def test_concurrent_different_commands_cannot_double_charge(setup):
    client, _, _ = setup
    response, headers, _ = start(client)
    view = move(client, headers, response.json(), 14, 9)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(lambda _: action(client, headers, view, {"kind": "interact", "target": "mara"}), range(2))
        )
    assert sorted(r.status_code for r in responses) == [200, 409]
    loaded = client.get("/v1/sessions/" + view["session_id"], headers=headers).json()
    assert loaded["state"]["visits"] == 1 and loaded["revision"] == view["revision"] + 1


def test_production_creation_rejects_connected_unsolvable_city(tmp_path):
    config, provider, calls, interest, _ = harness(tmp_path, "videogame")
    app = create_app(config, cultural_provider=provider)
    with TestClient(app) as client:
        gate = next(o for p in app.state.store.chapter.locations for o in p.objects if o.id == "beacon")
        for option in gate.choices:
            option.requires.append("nonexistent_key")
        response, headers, body = start_category(client, interest)
        assert response.status_code == 503 and response.json()["error"]["code"] == "CITY_UNSOLVABLE"
        duplicate = client.post("/v1/sessions", headers=headers, json=body)
        assert duplicate.status_code == 503 and len(calls) == 2
        with app.state.store.engine.connect() as connection:
            assert not connection.execute(select(games)).all()
            assert connection.execute(select(generations.c.status)).scalar_one() == "failed"


def test_legacy_zero_visit_state_remains_invalid():
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="Legacy travel"):
        GameState.model_validate({"visits": 0})
    assert fresh().visits == 0
