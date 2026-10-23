"""Deterministic saved-evidence/control integration, not live providers/models."""

import json
import os
import secrets
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.agent_tools import catalogue, execute
from backend.app.content import make_chapter
from backend.app.engine import apply_command, game_view
from backend.app.main import create_app
from backend.app.models import ActionRequest, Command, GameState, GenericControl, NewGame, SavedInterest
from backend.app.providers import CulturalProvider
from backend.app.solvability import activate_candidate, solve
from backend.app.taste_card import build
from backend.app.understanding import witness
from backend.tests.test_city_generation import initial, structure
from backend.tests.test_cultural_production import captured, envelope, harness
from backend.tests.test_service import action, goto_object, start


def finish(client, headers, view):
    """Execute solver witness through real Store receipts; semantic doubles only."""
    state = GameState.model_validate(view["state"])
    commands, _ = solve(client.app.state.store.chapter, state)
    token = headers["Authorization"].split()[1]
    last_request = None
    for raw in commands:
        state = GameState.model_validate(view["state"])
        command = Command.model_validate(raw)
        request = ActionRequest(request_id=uuid4(), expected_revision=view["revision"], command=command)
        assessment = (
            witness(state, command.target, command.choice)
            if command.kind == "choose" and state.cultural_context
            else None
        )
        with client.app.state.store.engine.begin() as connection:
            view = client.app.state.store._apply(
                connection, view["session_id"], token, request, understanding=assessment
            )
        last_request = request
    return view, last_request


@pytest.mark.parametrize("category", ["artist", "movie", "brand", "videogame"])
@pytest.mark.parametrize("ending", ["together", "keeper", "dawn"])
def test_cards_for_all_paths_and_endings(tmp_path, category, ending):
    state = activate_candidate(make_chapter(), initial(tmp_path, category))
    _, final = solve(make_chapter(), state)
    final.ending, final.taste_card = ending, None
    card = build(final)
    assert card == build(GameState.model_validate(final.model_dump(mode="json")))
    assert card.domain == "qloo" and card.ending == ending
    assert (
        card.profile
        == {
            "artist": "Sound-to-screen explorer",
            "movie": "Screen-to-sound explorer",
            "brand": "Design-to-screen explorer",
            "videogame": "Play-to-screen explorer",
        }[category]
    )
    assert "Application heuristic" in card.profile_basis
    assert card.relationships and card.encountered and card.discoveries
    excluded = {str(e.entity_id) for e in card.encountered}
    assert len({r.target.entity_id for r in card.try_next}) == len(card.try_next)
    for recommendation in card.try_next:
        assert str(recommendation.target.entity_id) not in excluded
        assert recommendation.provenance and "Aggregate affinity" in recommendation.explanation
        link = next(
            link for link in final.cultural_context.links if link.seed.entity_id == recommendation.source.entity_id
        )
        assert recommendation.target in link.recommendations


def test_profile_sparse_tags_and_empty_recommendations(tmp_path):
    state = initial(tmp_path)
    state.ending = "dawn"
    for link in state.cultural_context.links:
        link.seed.tags = []
        link.supporting_tag_id = ""
        for entity in link.recommendations:
            entity.tags = []
    card = build(state)
    assert card.profile == "First-light explorer" and not card.metadata_labels
    assert "unavailable" in card.profile_basis and not card.relationships
    # An uncompleted seed still gets supported suggestions; no invented filler.
    assert card.try_next
    link = state.cultural_context.links[0]
    link.recommendations = [next(e for e in link.recommendations if e.entity_id == link.selected_id)]
    state.flags = ["trace_0"]
    card = build(state)
    assert not card.try_next and "No additional supported" in card.recommendations_note


def test_recommendation_dedup_and_all_favourites_excluded(tmp_path):
    state = initial(tmp_path)
    state.cultural_context.links.append(state.cultural_context.links[0].model_copy(deep=True))
    link = state.cultural_context.links[0]
    chosen = link.recommendations[-1]
    state.interests.append(SavedInterest(name=chosen.name, category=chosen.category, entity_id=chosen.entity_id))
    state.ending = "dawn"
    card = build(state)
    ids = [r.target.entity_id for r in card.try_next]
    assert chosen.entity_id not in ids and len(ids) == len(set(ids))
    # Response ordering doesn't change the card.
    for link in state.cultural_context.links:
        link.recommendations.reverse()
    assert build(state) == card


@pytest.mark.parametrize("mode", ["authored", "generic_control"])
def test_non_qloo_cards_never_invent_recommendations(mode):
    state = GameState(
        mode=mode,
        generic_control=GenericControl() if mode == "generic_control" else None,
        visit_rules="conversation-v1",
        visits=0,
    )
    state = activate_candidate(make_chapter(), state)
    _, final = solve(make_chapter(), state)
    assert final.visits <= 12 and final.taste_card
    assert not final.taste_card.try_next and not final.taste_card.encountered
    assert not final.taste_card.relationships
    if mode == "generic_control":
        assert "control_proof" in final.flags and final.taste_card.domain == "invented_demo"
        assert not catalogue(final)
        assert final.taste_card.profile == "Lantern storyteller"


def test_synthetic_cannot_be_promoted_or_injected(tmp_path):
    cultural = initial(tmp_path)
    for data in (
        {**cultural.model_dump(), "generic_control": GenericControl()},
        {"mode": "generic_control", "generic_control": GenericControl(), "cultural_source": "qloo"},
        {"mode": "generic_control"},
    ):
        with pytest.raises(ValidationError):
            GameState.model_validate(data)
    with pytest.raises(ValidationError):
        GenericControl(source="qloo")
    with pytest.raises(ValidationError):
        NewGame(request_id=uuid4(), mode="generic_control", cultural_context=cultural.cultural_context)


def test_synthetic_tools_and_proof_do_not_claim_qloo_affinity(tmp_path):
    state = activate_candidate(
        make_chapter(),
        GameState(mode="generic_control", generic_control=GenericControl(), visit_rules="conversation-v1", visits=0),
    )
    view = game_view(make_chapter(), state, "synthetic", 0)
    assert execute(make_chapter(), view, "search_entities", {"query": "Lantern"}).status == "empty"
    result = execute(make_chapter(), view, "inspect_connection", {"pair": "selected"})
    assert result.status != "supported" and not result.provenance
    _, final = solve(make_chapter(), state)
    assert "control_proof" in final.flags and not any(f.startswith("proof_") for f in final.flags)
    cultural = activate_candidate(make_chapter(), initial(tmp_path))
    from backend.app.models import DomainError

    for candidate, invalid in ((cultural, "control_proof"), (state, "prove_0_affinity")):
        candidate.location_id, candidate.x, candidate.y = "station", 14, 9
        with pytest.raises(DomainError):
            apply_command(make_chapter(), candidate, Command(kind="choose", target="beacon", choice=invalid))


def test_concurrent_control_creation_is_one_owned_run_and_mode_is_bound(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    from sqlalchemy import select

    from backend.app.store import games

    config, provider, calls, interest, _ = harness(tmp_path, "artist")
    headers = {"Authorization": "Bearer " + secrets.token_urlsafe(32)}
    body = {"request_id": str(uuid4()), "mode": "generic_control", "interests": [interest]}
    with TestClient(create_app(config, cultural_provider=provider)) as client:

        def create(_):
            return client.post("/v1/sessions", headers=headers, json=body)

        with ThreadPoolExecutor(max_workers=3) as pool:
            responses = list(pool.map(create, range(3)))
        assert all(r.status_code == 200 for r in responses)
        assert len({r.json()["session_id"] for r in responses}) == 1
        assert all(r.json()["state"]["visits"] == 0 and not r.json()["state"]["flags"] for r in responses)
        assert not calls
        conflict = client.post("/v1/sessions", headers=headers, json={**body, "mode": "cultural"})
        assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
        assert not calls  # conflict check precedes provider use
        with client.app.state.store.engine.connect() as connection:
            assert len(connection.execute(select(games)).all()) == 1


@pytest.mark.parametrize("mode", ["cultural", "generic_control"])
@pytest.mark.parametrize("database", ["sqlite", "postgres"])
def test_saved_cards_receipts_restart_ownership_and_no_mode_mutation(tmp_path, mode, database):
    config, provider, calls, interest, _ = harness(tmp_path, "artist")
    if database == "postgres":
        if not os.environ.get("IS_TEST_POSTGRES_URL"):
            pytest.skip("Requires explicitly disposable PostgreSQL")
        config = replace(config, database_url=os.environ["IS_TEST_POSTGRES_URL"])
    headers = {"Authorization": "Bearer " + secrets.token_urlsafe(32)}
    body = {"request_id": str(uuid4()), "mode": mode, "interests": [interest]}
    with TestClient(create_app(config, cultural_provider=provider)) as client:
        response = client.post("/v1/sessions", json=body, headers=headers)
        assert response.status_code == 200, response.text
        view = response.json()
        assert view["state"]["taste_card"] is None
        replay = client.post("/v1/sessions", json=body, headers=headers)
        assert replay.json()["session_id"] == view["session_id"]
        done, request = finish(client, headers, view)
        replay = client.post(
            f"/v1/sessions/{done['session_id']}/actions", headers=headers, json=request.model_dump(mode="json")
        )
        assert replay.status_code == 200 and replay.json()["idempotent_replay"]
        assert replay.json()["state"] == done["state"]
        assert done["state"]["taste_card"] and done["state"]["visits"] <= 12
        hostile = {
            "request_id": str(uuid4()),
            "expected_revision": done["revision"],
            "mode": "cultural",
            "command": {"kind": "inspect", "target": "beacon"},
        }
        assert (
            client.post(f"/v1/sessions/{done['session_id']}/actions", headers=headers, json=hostile).status_code == 422
        )
        assert (
            client.get(
                f"/v1/sessions/{done['session_id']}", headers={"Authorization": "Bearer " + secrets.token_urlsafe(32)}
            ).status_code
            == 404
        )
    assert len(calls) == (2 if mode == "cultural" else 0)  # MockTransport ONLY.
    with TestClient(create_app(replace(config, qloo_calls_allowed=False))) as client:
        loaded = client.get(f"/v1/sessions/{done['session_id']}", headers=headers)
        assert loaded.status_code == 200, loaded.text
        assert loaded.json()["state"] == done["state"] and loaded.json()["revision"] == done["revision"]


def test_dawn_creates_persisted_card_and_legacy_completed_save_is_read_only(tmp_path):
    from backend.app.config import Settings

    config = Settings(database_url="sqlite:///" + str(tmp_path / "dawn.sqlite3"), environment="test")
    app = create_app(config)
    with TestClient(app) as client:
        response, _, _ = start(client, mode="generic_control")
        view = response.json()
    # Alternate resident encounters without relying on wall-clock or travel costs.
    state = GameState.model_validate(view["state"])
    state.visits, state.encounter_id, state.x, state.y = 12, "mara", 14, 9
    ended, _ = apply_command(app.state.store.chapter, state, Command(kind="position", x=18, y=9))
    assert ended.ending == "dawn" and ended.taste_card.ending == "dawn"
    assert not ended.taste_card.relationships and ended.visits == 12
    legacy = ended.model_copy(update={"taste_card": None})
    one = game_view(app.state.store.chapter, legacy, "legacy", 0)
    assert one["state"]["taste_card"] and legacy.taste_card is None
    assert game_view(app.state.store.chapter, legacy, "legacy", 0) == one


@pytest.mark.parametrize("mode", ["cultural", "generic_control"])
@pytest.mark.parametrize("database", ["sqlite", "postgres"])
def test_actual_twelfth_encounter_dawn_card_persists_and_replays(tmp_path, mode, database):
    config, provider, calls, interest, _ = harness(tmp_path, "artist")
    if database == "postgres":
        if not os.environ.get("IS_TEST_POSTGRES_URL"):
            pytest.skip("Requires explicitly disposable PostgreSQL")
        config = replace(config, database_url=os.environ["IS_TEST_POSTGRES_URL"])
    headers = {"Authorization": "Bearer " + secrets.token_urlsafe(32)}
    with TestClient(create_app(config, cultural_provider=provider)) as client:
        view = client.post(
            "/v1/sessions", headers=headers, json={"request_id": str(uuid4()), "mode": mode, "interests": [interest]}
        ).json()
        for i in range(12):
            target = "mara" if i % 2 == 0 else "ivo"
            view = goto_object(client, headers, view, target)
            response = action(client, headers, view, {"kind": "interact", "target": target})
            assert response.status_code == 200, response.text
            view = response.json()
            assert view["state"]["visits"] == i + 1 and not view["state"]["ending"]
        rid = str(uuid4())
        command = {"kind": "position", "x": 18, "y": 9}
        response = action(client, headers, view, command, request_id=rid)
        assert response.status_code == 200, response.text
        ended = response.json()
        assert ended["state"]["ending"] == "dawn" and ended["state"]["taste_card"]["ending"] == "dawn"
        assert ended["state"]["taste_card"]["profile"] in ("First-light explorer", "Lantern storyteller")
        assert not ended["state"]["taste_card"]["relationships"]
        if mode == "generic_control":
            assert "0/3 motif milestones confirmed" in ended["state"]["taste_card"]["profile_basis"]
        replay = action(client, headers, view, command, request_id=rid)
        assert replay.json()["state"] == ended["state"] and replay.json()["idempotent_replay"]
        output = os.environ.get("IS_PHASE5_EVIDENCE_DIRECTORY")
        if output:
            folder = Path(output)
            folder.mkdir(exist_ok=True)
            name = "artist-on-dawn-ending.json" if mode == "cultural" else "artist-off-dawn-ending.json"
            (folder / name).write_text(json.dumps(ended, indent=2))
    with TestClient(create_app(replace(config, qloo_calls_allowed=False))) as client:
        assert client.get("/v1/sessions/" + ended["session_id"], headers=headers).json()["state"] == ended["state"]
    assert len(calls) == (2 if mode == "cultural" else 0)


def test_two_player_judging_and_mode_isolation(tmp_path):
    views, ends, signatures = [], [], []
    config, _, _, _, _ = harness(tmp_path, "artist")
    records = {category: captured(category) for category in ("artist", "movie")}
    calls = []

    def captured_transport(request):
        calls.append(request.url.path)
        assert request.url.host == "hackathon.api.qloo.com"
        if request.url.path == "/search":
            category = request.url.params["types"].removeprefix("urn:entity:")
            name, search, _, _ = records[category]
            assert request.url.params["query"] == name
            return httpx.Response(200, json=envelope(search))
        assert request.url.path == "/v2/insights"
        record = next(
            r
            for r in records.values()
            if r[3]["entity_id"].lower() == request.url.params["signal.interests.entities"].lower()
        )
        return httpx.Response(200, json=envelope(record[2]))

    provider = CulturalProvider(config, transport=httpx.MockTransport(captured_transport))
    owners = []
    same_creation_id = str(uuid4())  # Owner-scoped, never shared state/receipts.
    with TestClient(create_app(config, cultural_provider=provider)) as client:
        for category in ("artist", "movie"):
            name, _, _, seed = records[category]
            interest = {"name": name, "category": category, "entity_id": seed["entity_id"]}
            headers = {"Authorization": "Bearer " + secrets.token_urlsafe(32)}
            owners.append(headers)
            body = {"request_id": same_creation_id, "mode": "cultural", "interests": [interest]}
            cultural = client.post("/v1/sessions", headers=headers, json=body).json()
            body = {**body, "mode": "generic_control", "request_id": str(uuid4())}
            control = client.post("/v1/sessions", headers=headers, json=body).json()
            assert cultural["session_id"] != control["session_id"]
            before = client.get("/v1/sessions/" + cultural["session_id"], headers=headers).json()
            completed, _ = finish(client, headers, control)
            assert client.get("/v1/sessions/" + cultural["session_id"], headers=headers).json() == before
            state = GameState.model_validate(cultural["state"])
            synthetic = GameState.model_validate(control["state"])
            assert structure(state) != structure(synthetic)
            assert synthetic.cultural_context is None and not catalogue(synthetic)
            assert not synthetic.city_generation
            assert "control_proof" in completed["state"]["flags"]
            target = state.cultural_context.links[0].selected_id
            assert str(target) not in json.dumps(control)
            assert "synthetic" in " ".join(control["notices"]).lower()
            assert len(calls) == len(owners) * 2  # Only captured resolution/recommendation per cultural run.
            views.extend([cultural, control])
            cultural_done, _ = finish(client, headers, cultural)
            ends.extend([cultural_done, completed])
            signatures.append(structure(state))
        for index, view in enumerate(views):
            wrong_owner = owners[1 if index < 2 else 0]
            assert client.get("/v1/sessions/" + view["session_id"], headers=wrong_owner).status_code == 404
    assert signatures[0] != signatures[1]
    assert len({v["session_id"] for v in views}) == 4
    assert len({v["state"]["city_generation"]["seed"] for v in views if v["state"]["city_generation"]}) == 2
    output = os.environ.get("IS_PHASE5_EVIDENCE_DIRECTORY")
    if output:
        folder = Path(output)
        folder.mkdir(exist_ok=True)
        # Public snapshots contain no ownership tokens or request headers.
        for name, view in zip(("artist-on", "artist-off", "movie-on", "movie-off"), views, strict=True):
            (folder / (name + ".json")).write_text(json.dumps(view, indent=2))
        for name, view in zip(("artist-on", "artist-off", "movie-on", "movie-off"), ends, strict=True):
            (folder / (name + "-ending.json")).write_text(json.dumps(view, indent=2))
