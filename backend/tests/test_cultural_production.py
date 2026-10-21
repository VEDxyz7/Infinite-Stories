"""Production adapter/session tests: actual captured projections over MockTransport.

No live API access. HTTP envelope replay is reconstructed from the observed
containers, not claimed to be the original full upstream body. Missing private
captures skip explicitly; synthetic data is used only for negative cases.
"""

import json
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import DomainError, Interest
from backend.app.providers import CulturalProvider
from backend.app.store import games, generations, qloo_budget
from backend.tests.test_service import action, choose, move, start, visit_next

ROOT = Path(__file__).resolve().parents[2]
PAIRS = {
    "artist": ("David Bowie", "qloo-cross-category-20261020", 1),
    "movie": ("Spirited Away", "qloo-cross-category-20261020", 3),
    "brand": ("LEGO", "qloo-remaining-categories-20261020", 3),
    "videogame": ("The Legend of Zelda: Breath of the Wild", "qloo-remaining-categories-20261020", 5),
}


def captured(category):
    name, folder, first = PAIRS[category]
    paths = [ROOT / "reports/local" / folder / f"request-{i}.json" for i in (first, first + 1)]
    if not all(p.is_file() for p in paths):
        pytest.skip("Actual private captures missing; no positive synthetic fallback")
    search, recs = [json.loads(p.read_text()) for p in paths]
    seed = next(
        e for e in search["entities"] if e["entity_id"].lower() == recs["params"]["signal.interests.entities"].lower()
    )
    return name, search, recs, seed


def envelope(record):
    entities = []
    for entity in record["entities"]:
        entities.append(
            {
                k: v
                for k, v in entity.items()
                if k
                in (
                    "entity_id",
                    "name",
                    "type",
                    "types",
                    "subtype",
                    "properties",
                    "tags",
                    "disambiguation",
                    "popularity",
                )
            }
        )
    return (
        {"results": entities} if record["path"] == "/search" else {"success": True, "results": {"entities": entities}}
    )


def harness(tmp_path, category, responder=None, **overrides):
    name, search, recs, seed = captured(category)
    calls = []
    config = Settings(
        database_url="sqlite:///" + str(tmp_path / "culture.sqlite3"),
        environment="test",
        requests_per_minute=1000,
        qloo_key="TEST_ONLY_NOT_A_CREDENTIAL",
        qloo_calls_allowed=True,
        qloo_min_interval=0,
        **overrides,
    )

    def handler(request):
        calls.append(request)
        assert request.method == "GET"
        assert request.url.host == "hackathon.api.qloo.com"
        assert request.url.scheme == "https"
        assert request.url.params["take"] == "5"
        assert request.headers["x-api-key"] == config.qloo_key
        if responder:
            return responder(request)
        if request.url.path == "/search":
            assert request.url.params["types"] == "urn:entity:" + category
            assert request.url.params["query"] == name
            return httpx.Response(200, json=envelope(search))
        assert request.url.path == "/v2/insights"
        assert request.url.params["signal.interests.entities"].lower() == seed["entity_id"].lower()
        assert request.url.params["filter.type"] == "urn:entity:" + ("artist" if category == "movie" else "movie")
        return httpx.Response(200, json=envelope(recs))

    provider = CulturalProvider(config, transport=httpx.MockTransport(handler))
    interest = {"name": name, "category": category, "entity_id": seed["entity_id"]}
    return config, provider, calls, interest, recs


@pytest.mark.parametrize("category", list(PAIRS))
@pytest.mark.parametrize("database", ["sqlite", "postgres"])
def test_real_adapter_creates_required_cultural_quest_and_persists_across_restart(tmp_path, category, database):
    config, provider, calls, interest, recs = harness(tmp_path, category)
    if database == "postgres":
        if not os.getenv("IS_TEST_POSTGRES_URL"):
            pytest.skip("Requires real disposable PostgreSQL; no substitute")
        config = replace(config, database_url=os.environ["IS_TEST_POSTGRES_URL"])
    headers = {"Authorization": "Bearer " + secrets.token_urlsafe(32)}
    body = {"request_id": str(uuid4()), "mode": "cultural", "interests": [interest]}
    with TestClient(create_app(config, cultural_provider=provider)) as client:
        result = client.post("/v1/sessions", headers=headers, json=body)
        assert result.status_code == 200, result.text
        view = result.json()
        context = view["state"]["cultural_context"]
        assert view["state"]["cultural_source"] == "qloo"
        link = context["links"][0]
        assert {e["entity_id"].lower() for e in link["recommendations"]} == {
            e["entity_id"].lower() for e in recs["entities"]
        }
        assert link["seed"]["entity_id"].lower() == interest["entity_id"].lower()
        assert link["seed"]["category"] == category
        assert all(e["category"] == ("artist" if category == "movie" else "movie") for e in link["recommendations"])
        assert link["evidence"][1]["params"]["signal.interests.entities"].lower() == interest["entity_id"].lower()
        assert [p["path"] for p in link["evidence"]] == ["/search", "/v2/insights"]
        assert all(
            p["origin"] == "https://hackathon.api.qloo.com" and len(p["body_sha256"]) == 64 for p in link["evidence"]
        )
        # Assert against captured fields, independently of the production parser.
        originals = {e["entity_id"].lower(): e for e in recs["entities"]}
        for entity in link["recommendations"]:
            original = originals[entity["entity_id"].lower()]
            props = original.get("properties", {})
            assert entity["name"] == original["name"]
            assert entity["year"] == props.get("release_year")
            assert entity["content_rating"] == (props.get("content_rating") or "")
            assert entity["description"] == (props.get("description") or props.get("short_description") or "")[:400]
            source_tags = {t.get("id") or t.get("tag_id"): t for t in original.get("tags", [])}
            assert entity["tags"]
            for tag in entity["tags"]:
                assert tag["id"] in source_tags
                assert tag["name"] == source_tags[tag["id"]]["name"]
                assert tag["type"] == source_tags[tag["id"]]["type"]
        selected = next(e for e in link["recommendations"] if e["entity_id"] == link["selected_id"])
        assert link["supporting_tag_id"] in {t["id"] for t in selected["tags"]}
        assert len(calls) == 2
        replay = client.post("/v1/sessions", headers=headers, json=body)
        assert replay.status_code == 200 and replay.json()["session_id"] == view["session_id"] and len(calls) == 2
        view = choose(client, headers, view, "mara", "take_map")
        view = choose(client, headers, visit_next(client, headers, view), "ivo", "learn_rhythm")
        view = move(client, headers, visit_next(client, headers, view), 14, 9)
        blocked = action(client, headers, view, {"kind": "choose", "target": "sera", "choice": "promise_guard"})
        assert blocked.status_code == 409
        card = next(o for o in view["location"]["objects"] if o["id"] == "cultural_echo_0")
        view = move(client, headers, view, card["x"], card["y"])
        bad = action(client, headers, view, {"kind": "choose", "target": card["id"], "choice": "fabricated"})
        assert bad.status_code == 409
        good = action(
            client, headers, view, {"kind": "choose", "target": card["id"], "choice": card["choices"][0]["id"]}
        )
        assert good.status_code == 200, good.text
        view = choose(client, headers, good.json(), "sera", "promise_guard")
        view = choose(client, headers, visit_next(client, headers, view), "beacon", "light_together")
        assert view["state"]["ending"] == "together" and view["state"]["visits"] == 4
    # No provider configured on restarted process; existing context is sufficient.
    with TestClient(create_app(replace(config, qloo_calls_allowed=False, qloo_key=""))) as restarted:
        restored = restarted.get("/v1/sessions/" + view["session_id"], headers=headers)
        assert restored.status_code == 200, restored.text
        assert restored.json()["state"] == view["state"]
        assert restarted.post("/v1/sessions", headers=headers, json=body).json()["state"] == view["state"]
        assert len(calls) == 2


@pytest.mark.parametrize(
    "status,expected",
    [
        (400, "QLOO_REQUEST_REJECTED"),
        (401, "QLOO_AUTH"),
        (403, "QLOO_AUTH"),
        (429, "QLOO_RATE_LIMIT"),
        (500, "QLOO_UPSTREAM"),
        (302, "QLOO_UPSTREAM"),
    ],
)
@pytest.mark.parametrize("category", list(PAIRS))
@pytest.mark.parametrize("stage", ["/search", "/v2/insights"])
def test_http_failures_terminal_no_retry_no_partial_session(tmp_path, status, expected, caplog, category, stage):
    _, search, _, _ = captured(category)

    def fail(request):
        if request.url.path != stage:
            return httpx.Response(200, json=envelope(search))
        return httpx.Response(status, json={"errors": ["DO_NOT_ECHO_PRIVATE_ERROR"]})

    config, provider, calls, interest, _ = harness(tmp_path, category, fail)
    with TestClient(create_app(config, cultural_provider=provider)) as client:
        authored, headers, _ = start(client)
        prior = choose(client, headers, authored.json(), "mara", "take_map")
        body = {"request_id": str(uuid4()), "mode": "cultural", "interests": [interest]}
        result = client.post("/v1/sessions", headers=headers, json=body)
        assert result.json()["error"]["code"] == expected
        assert client.post("/v1/sessions", headers=headers, json=body).json()["error"]["code"] == expected
        assert len(calls) == (1 if stage == "/search" else 2)
        assert "DO_NOT_ECHO" not in result.text + caplog.text
        with client.app.state.store.engine.connect() as connection:
            assert len(connection.execute(select(games)).all()) == 1
            assert connection.execute(select(generations.c.status)).scalar_one() == "failed"
        loaded = client.get("/v1/sessions/" + prior["session_id"], headers=headers).json()
        assert loaded["state"] == prior["state"] and loaded["revision"] == prior["revision"]


@pytest.mark.parametrize(
    "case,code",
    [
        ("timeout", "QLOO_TIMEOUT"),
        ("network", "QLOO_NETWORK"),
        ("malformed", "QLOO_RESPONSE_INVALID"),
        ("shape", "QLOO_RESPONSE_INVALID"),
        ("empty", "QLOO_EMPTY"),
        ("wrong_category", "QLOO_UNUSABLE"),
    ],
)
@pytest.mark.parametrize("category", list(PAIRS))
def test_transport_and_payload_failures(tmp_path, case, code, category):
    name, search, recs, _ = captured(category)

    def fail(request):
        if request.url.path == "/search":
            return httpx.Response(200, json=envelope(search))
        if case == "timeout":
            raise httpx.ReadTimeout("PRIVATE", request=request)
        if case == "network":
            raise httpx.ConnectError("PRIVATE", request=request)
        if case == "malformed":
            return httpx.Response(200, content=b"not json")
        if case == "shape":
            return httpx.Response(200, json={"results": []})
        if case == "empty":
            return httpx.Response(200, json={"success": True, "results": {"entities": []}})
        body = envelope(recs)
        for e in body["results"]["entities"]:
            e["subtype"] = "urn:entity:book"
        return httpx.Response(200, json=body)

    _, provider, calls, interest, _ = harness(tmp_path, category, fail)
    with pytest.raises(DomainError, match=code):
        provider.generate([Interest.model_validate(interest)])
    assert len(calls) == 2


def test_ambiguous_brand_requires_actual_candidate_confirmation_and_uses_cache(tmp_path):
    config, provider, calls, interest, _ = harness(tmp_path, "brand")
    with TestClient(create_app(config, cultural_provider=provider)) as client:
        headers = {"Authorization": "Bearer " + secrets.token_urlsafe(32)}
        bare = {"name": "LEGO", "category": "brand"}
        first = client.post(
            "/v1/sessions", headers=headers, json={"request_id": str(uuid4()), "mode": "cultural", "interests": [bare]}
        )
        assert first.status_code == 409 and first.json()["error"]["code"] == "QLOO_AMBIGUOUS"
        assert first.json()["error"]["details"]["candidates"][0]["name"] == "The Lego Group"
        confirmed = client.post(
            "/v1/sessions",
            headers=headers,
            json={"request_id": str(uuid4()), "mode": "cultural", "interests": [interest]},
        )
        assert confirmed.status_code == 200, confirmed.text
        assert len(calls) == 2  # Search cached, one recommendation fetch.


def test_books_and_unknown_inputs_rejected_before_transport(tmp_path):
    config, provider, calls, interest, _ = harness(tmp_path, "artist")
    with TestClient(create_app(config, cultural_provider=provider)) as client:
        for category in ("book", "unknown"):
            response = client.post(
                "/v1/sessions",
                headers={"Authorization": "Bearer " + secrets.token_urlsafe(32)},
                json={
                    "request_id": str(uuid4()),
                    "mode": "cultural",
                    "interests": [{"name": "Dune", "category": category}],
                },
            )
            assert response.status_code == 422
        assert calls == []


@pytest.mark.parametrize("category", list(PAIRS))
@pytest.mark.parametrize(
    "case,code",
    [
        ("ambiguous", "QLOO_AMBIGUOUS"),
        ("empty", "QLOO_EMPTY"),
        ("invalid_id", "QLOO_RESPONSE_INVALID"),
        ("wrong_category", "QLOO_RESPONSE_INVALID"),
    ],
)
def test_invalid_resolution_never_sends_dependent_request(tmp_path, category, case, code):
    _, search, _, seed = captured(category)
    body = envelope(search)
    body["results"] = [next(e for e in body["results"] if e["entity_id"] == seed["entity_id"])]
    if case == "ambiguous":
        # Deliberately synthetic duplicate identity is a negative fixture only.
        duplicate = {**body["results"][0], "entity_id": str(uuid4())}
        body["results"].append(duplicate)
    elif case == "empty":
        body["results"] = []
    elif case == "invalid_id":
        body["results"][0]["entity_id"] = "not-an-entity-id"
    else:
        body["results"][0]["subtype"] = "urn:entity:book"

    def respond(request):
        assert request.url.path == "/search"
        assert request.url.params["types"] == "urn:entity:" + category
        return httpx.Response(200, json=body)

    _, provider, calls, _, _ = harness(tmp_path, category, respond)
    with pytest.raises(DomainError, match=code):
        provider.generate([Interest(name=seed["name"], category=category)])
    assert len(calls) == 1


def test_durable_budget_and_same_seed_multicard_choice_ids(tmp_path):
    config, provider, calls, interest, _ = harness(tmp_path, "artist", qloo_daily_requests=2)
    with TestClient(create_app(config, cultural_provider=provider)) as client:
        body = {"request_id": str(uuid4()), "mode": "cultural", "interests": [interest, interest]}
        result = client.post(
            "/v1/sessions", headers={"Authorization": "Bearer " + secrets.token_urlsafe(32)}, json=body
        )
        assert result.status_code == 200, result.text
        assert len(result.json()["state"]["cultural_context"]["links"]) == 2 and len(calls) == 2
        with client.app.state.store.engine.connect() as connection:
            assert connection.execute(select(qloo_budget.c.used)).scalar_one() == 2
        with pytest.raises(DomainError, match="QLOO_APP_BUDGET"):
            client.app.state.store.reserve_qloo_request(2)


def test_concurrent_duplicate_creation_does_not_repeat_provider(tmp_path):
    config, provider, calls, interest, _ = harness(tmp_path, "artist")
    with TestClient(create_app(config, cultural_provider=provider)) as client:
        body = {"request_id": str(uuid4()), "mode": "cultural", "interests": [interest]}
        headers = {"Authorization": "Bearer " + secrets.token_urlsafe(32)}
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: client.post("/v1/sessions", headers=headers, json=body), range(2)))
        assert all(x.status_code in (200, 409) for x in results)
        assert any(x.status_code == 200 for x in results)
        assert len(calls) == 2
        replay = client.post("/v1/sessions", headers=headers, json=body)
        assert replay.status_code == 200
