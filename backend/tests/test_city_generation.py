"""Saved/captured-fixture city generation. No live providers or model inference."""

from dataclasses import replace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.city_generation import distance, evidence_paths, generate
from backend.app.content import make_chapter
from backend.app.culture import chapter_for_state
from backend.app.main import create_app
from backend.app.models import DomainError, GameState, NewGame
from backend.app.solvability import MAX_CANDIDATES, activate_candidate, solve
from backend.tests.test_cultural_production import harness


def initial(tmp_path, category="artist"):
    _, provider, calls, interest, _ = harness(tmp_path, category)
    context = provider.generate(NewGame(request_id=uuid4(), mode="cultural", interests=[interest]).interests)
    assert len(calls) == 2  # MockTransport; not actual provider usage.
    return GameState(
        mode="cultural", cultural_source="qloo", cultural_context=context, visit_rules="conversation-v1", visits=0
    )


def structure(state):
    chapter = chapter_for_state(make_chapter(), state)
    return [
        (
            loc.id,
            [
                (o.id.split("_")[0], o.kind, o.x, o.y, o.destination, [c.requires for c in o.choices if c.grants])
                for o in loc.objects
            ],
        )
        for loc in chapter.locations
    ]


@pytest.mark.parametrize("category", ["artist", "movie", "brand", "videogame"])
def test_saved_plan_is_reproducible_and_executable(tmp_path, category):
    s = initial(tmp_path, category)
    a = activate_candidate(make_chapter(), s)
    b = activate_candidate(make_chapter(), GameState.model_validate(s.model_dump(mode="json")))
    assert a.model_dump() == b.model_dump()
    assert a.city_generation and a.activation_validation.generation_sha256
    commands, final = solve(make_chapter(), a)
    assert commands and final.ending in ("together", "keeper") and final.visits <= 12
    resumed = GameState.model_validate(a.model_dump(mode="json"))
    assert chapter_for_state(make_chapter(), resumed) == chapter_for_state(make_chapter(), a)
    assert not a.flags and not a.understanding_records
    assert all(e.relationship == "direct_saved_recommendation" for e in a.city_generation.distances)


def test_different_favourites_change_structure_not_only_ids_or_text(tmp_path):
    states = [
        activate_candidate(make_chapter(), initial(tmp_path / c, c)) for c in ("artist", "movie", "brand", "videogame")
    ]
    signatures = {repr(structure(s)) for s in states}
    assert len(signatures) >= 2
    assert len({str(s.cultural_context.links[0].selected_id) for s in states}) >= 2
    assert len({s.city_generation.seed for s in states}) == 4


def test_tag_contrast_is_application_jaccard_not_category_or_randomness(tmp_path):
    s = initial(tmp_path)
    seed = s.cultural_context.links[0].seed
    identical = seed.model_copy(deep=True)
    result = distance(seed, identical)
    assert result.contrast == 0 and result.shared_tags
    sparse = identical.model_copy(update={"tags": []})
    assert distance(seed, sparse).contrast is None
    assert distance(seed, sparse).metadata_status == "unknown"
    assert distance(seed, sparse).comparable_domains == []
    link = s.cultural_context.links[0]
    assert evidence_paths(s.cultural_context, link.seed.entity_id, link.recommendations[0].entity_id)
    assert not evidence_paths(s.cultural_context, link.recommendations[0].entity_id, link.seed.entity_id)
    assert not evidence_paths(s.cultural_context, uuid4(), uuid4())


def test_plan_seeds_change_real_routes_and_missing_metadata_is_not_far(tmp_path):
    s = initial(tmp_path)
    for link in s.cultural_context.links:
        link.seed.tags = []
        for entity in link.recommendations:
            entity.tags = []
        link.supporting_tag_id = ""
    plans = []
    templates = set()
    for seed in ("a" * 64, "b" * 64, "c" * 64, "d" * 64, "e" * 64):
        context, plan = generate(s.cultural_context, 0, seed)
        candidate = s.model_copy(update={"cultural_context": context, "city_generation": plan})
        _, final = solve(make_chapter(), candidate)
        assert final.visits <= 12
        assert all(d.contrast is None and d.metadata_status == "unknown" for d in plan.distances)
        plans.append(repr(structure(candidate)))
        templates.add(plan.template)
    assert templates == {0, 1, 2}
    assert len(set(plans)) >= 3


def test_unsolvable_candidate_regenerates_bounded_without_providers(tmp_path, monkeypatch):
    import backend.app.solvability as solver

    state = initial(tmp_path)
    original = solver.solve
    seen = []

    def reject_first(base, candidate):
        seen.append(candidate.city_generation.model_dump())
        if len(seen) == 1:
            raise ValueError("Controlled connected but semantically invalid candidate")
        return original(base, candidate)

    monkeypatch.setattr(solver, "solve", reject_first)
    accepted = activate_candidate(make_chapter(), state)
    assert len(seen) == 2 and accepted.activation_validation.candidate == 1
    assert seen[0] != seen[1]
    monkeypatch.setattr(solver, "solve", lambda *_: (_ for _ in ()).throw(ValueError("No path")))
    with pytest.raises(DomainError, match="CITY_UNSOLVABLE"):
        activate_candidate(make_chapter(), state)
    assert state.city_generation is None and not state.flags


@pytest.mark.parametrize("database", ["sqlite", "postgres"])
def test_production_plan_persists_and_provider_free_restart(tmp_path, database):
    import secrets

    config, provider, calls, interest, _ = harness(tmp_path, "brand")
    if database == "postgres":
        import os

        if not os.getenv("IS_TEST_POSTGRES_URL"):
            pytest.skip("Requires disposable PostgreSQL")
        config = replace(config, database_url=os.environ["IS_TEST_POSTGRES_URL"])
    headers = {"Authorization": "Bearer " + secrets.token_urlsafe(32)}
    with TestClient(create_app(config, cultural_provider=provider)) as client:
        body = {"request_id": str(uuid4()), "mode": "cultural", "interests": [interest]}
        response = client.post("/v1/sessions", headers=headers, json=body)
        assert response.status_code == 200, response.text
        view = response.json()
        assert view["state"]["city_generation"]
        replay = client.post("/v1/sessions", headers=headers, json=body).json()
        assert replay["state"] == view["state"] and replay["session_id"] == view["session_id"]
    with TestClient(create_app(replace(config, qloo_calls_allowed=False, qloo_key=""))) as fresh:
        saved = fresh.get("/v1/sessions/" + view["session_id"], headers=headers)
        assert saved.status_code == 200 and saved.json()["state"] == view["state"]
    assert len(calls) == 2


def test_five_link_procedural_path_and_resident_assignments(tmp_path):
    from backend.app.understanding import topic

    s = initial(tmp_path)
    s.cultural_context.links *= 5  # Controlled stress fixture, not five live-resolved favourites.
    candidate = activate_candidate(make_chapter(), s)
    commands, final = solve(make_chapter(), candidate)
    assert final.visits <= 12 and all(f"proof_{i}" in final.flags for i in range(5))
    assert len(candidate.city_generation.proof_order) == 5
    for resident, index in candidate.city_generation.resident_links.items():
        assert topic(candidate, resident)["link_index"] == index
    chosen = [c["choice"] for c in commands if c["kind"] == "choose" and c["choice"].startswith("prove_")]
    assert [int(c.split("_")[1]) for c in chosen] == candidate.city_generation.proof_order


def test_plan_metadata_and_seed_are_not_client_authority(tmp_path):
    import secrets

    from pydantic import ValidationError

    s = activate_candidate(make_chapter(), initial(tmp_path))
    modified = s.model_dump(mode="json")
    modified["city_generation"]["distances"][0]["source_id"] = str(uuid4())
    with pytest.raises(ValidationError):
        GameState.model_validate(modified)
    cfg, provider, _, interest, _ = harness(tmp_path / "api", "brand")
    with TestClient(create_app(cfg, cultural_provider=provider)) as client:
        result = client.post(
            "/v1/sessions",
            headers={"Authorization": "Bearer " + secrets.token_urlsafe(32)},
            json={
                "request_id": str(uuid4()),
                "mode": "cultural",
                "interests": [interest],
                "city_generation": s.city_generation.model_dump(mode="json"),
            },
        )
        assert result.status_code == 422


def test_empty_evidence_is_rejected_before_city_activation(tmp_path):
    from pydantic import ValidationError

    state = initial(tmp_path)
    state.cultural_context.links[0].recommendations = []
    with pytest.raises(ValidationError):
        activate_candidate(make_chapter(), state)


def test_multiple_real_capture_favourites_have_executable_ordered_proof(tmp_path):
    from backend.app.understanding import topic

    states = [initial(tmp_path / category, category) for category in ("artist", "movie", "brand", "videogame")]
    state = states[0]
    state.cultural_context.links = [s.cultural_context.links[0] for s in states]
    candidate = activate_candidate(make_chapter(), state)
    commands, final = solve(make_chapter(), candidate)
    assert final.visits <= 12 and len(candidate.city_generation.proof_order) == 4
    proof_order = [
        int(c["choice"].split("_")[1]) for c in commands if c["kind"] == "choose" and c["choice"].startswith("prove_")
    ]
    assert proof_order == candidate.city_generation.proof_order
    assert len({topic(candidate, r)["source"]["entity_id"] for r in ("mara", "ivo", "sera")}) == 3


def test_generation_metadata_domains_are_not_interchangeable(tmp_path):
    s = initial(tmp_path)
    seed = s.cultural_context.links[0].seed
    other = seed.model_copy(deep=True)
    for tag in other.tags:
        tag.type = "controlled-fixture:incomparable-domain"
    assert distance(seed, other).contrast is None
    assert not distance(seed, other).shared_tags


def test_regeneration_attempts_are_exactly_bounded(tmp_path, monkeypatch):
    import backend.app.solvability as solver

    state = initial(tmp_path)
    seen = []

    def impossible(base, candidate):
        seen.append(candidate.city_generation.candidate)
        raise ValueError("Controlled impossible candidate")

    monkeypatch.setattr(solver, "solve", impossible)
    with pytest.raises(DomainError, match="CITY_UNSOLVABLE"):
        activate_candidate(make_chapter(), state)
    assert seen == list(range(MAX_CANDIDATES)) == [0, 1, 2]


def test_actual_missing_gate_prerequisite_is_rejected_before_activation(tmp_path):
    state = initial(tmp_path)
    chapter = make_chapter()
    gate = next(o for loc in chapter.locations for o in loc.objects if o.id == "beacon")
    for choice in gate.choices:
        choice.requires.append("unobtainable-fixture-flag")
    with pytest.raises(DomainError, match="CITY_UNSOLVABLE"):
        activate_candidate(chapter, state)
    assert state.activation_validation is None and not state.flags


def test_changed_saved_seed_is_rejected_without_overwriting_saved_progress(tmp_path):
    import secrets

    from sqlalchemy import update

    from backend.app.store import digest, games

    cfg, provider, _, interest, _ = harness(tmp_path, "artist")
    headers = {"Authorization": "Bearer " + secrets.token_urlsafe(32)}
    with TestClient(create_app(cfg, cultural_provider=provider)) as client:
        view = client.post(
            "/v1/sessions",
            headers=headers,
            json={"request_id": str(uuid4()), "mode": "cultural", "interests": [interest]},
        ).json()
        bad = view["state"]
        bad["city_generation"]["seed"] = "f" * 64
        with client.app.state.store.engine.begin() as connection:
            connection.execute(
                update(games).where(games.c.id == view["session_id"]).values(state=bad, state_hash=digest(bad))
            )
        result = client.get("/v1/sessions/" + view["session_id"], headers=headers)
        assert result.status_code == 503 and result.json()["error"]["code"] == "SAVE_INVALID"


def test_provider_result_and_tag_order_do_not_change_city_seed(tmp_path):
    s = initial(tmp_path)
    changed = s.cultural_context.model_copy(deep=True)
    for link in changed.links:
        link.seed.tags.reverse()
        link.recommendations.reverse()
        for entity in link.recommendations:
            entity.tags.reverse()
    first, a = generate(s.cultural_context, 0)
    second, b = generate(changed, 0)
    assert a == b
    assert [link.selected_id for link in first.links] == [link.selected_id for link in second.links]


def test_presentation_copy_does_not_invalidate_generated_gameplay_fingerprint(tmp_path, monkeypatch):
    import backend.app.culture as culture
    from backend.app.solvability import initial_chapter_fingerprint

    state = activate_candidate(make_chapter(), initial(tmp_path))
    before = initial_chapter_fingerprint(make_chapter(), state)
    original = culture.dress_chapter

    def wording(chapter, saved):
        chapter = original(chapter, saved)
        for loc in chapter.locations:
            loc.description += " Controlled presentation-only revision."
            for obj in loc.objects:
                obj.text += " Controlled presentation-only revision."
        return chapter

    monkeypatch.setattr(culture, "dress_chapter", wording)
    assert initial_chapter_fingerprint(make_chapter(), state) == before


def test_centre_cannot_be_another_selected_favourite(tmp_path):
    states = [initial(tmp_path / category, category) for category in ("artist", "movie", "brand", "videogame")]
    state = states[0]
    state.cultural_context.links = [s.cultural_context.links[0] for s in states]
    chosen = activate_candidate(make_chapter(), state)
    favourites = {link.seed.entity_id for link in chosen.cultural_context.links}
    assert all(link.selected_id not in favourites for link in chosen.cultural_context.links)


def test_only_favourite_results_fail_bounded_without_inventing_a_centre(tmp_path):
    # A deliberately inconsistent nested provider DOUBLE: parent validation is
    # bypassed only to exercise selection's own known-favourite rejection.
    # No synthetic relationship is ever activated or described as Qloo evidence.
    import backend.app.city_generation as generation

    s = initial(tmp_path)
    context = s.cultural_context.model_copy(deep=True)
    link = context.links[0]
    link.recommendations = [link.seed]
    with pytest.raises(ValueError, match="outside the selected favourites"):
        generation.generate(context, 0)
