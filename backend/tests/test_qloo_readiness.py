"""Offline readiness audit. Replay captures are real; altered error records are synthetic.

No production Qloo transport exists. These tests do not pretend one is wired.
Missing private captures are explicitly skipped rather than replaced with fixtures.
"""

import copy
import json
import logging
import socket
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import DomainError
from backend.app.providers import CulturalProvider
from backend.app.store import games, receipts
from backend.tests.test_service import choose, start
from scripts.qloo_cross_category_decision import build_decision
from scripts.qloo_remaining_decision import build_decision as build_remaining_decision
from scripts.qloo_remaining_request import seed_candidates

ROOT = Path(__file__).resolve().parents[2]
CAPTURES = ROOT / "reports/local/qloo-cross-category-20261020"


@pytest.fixture(autouse=True)
def no_external_transport(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No network or subprocess permitted in readiness tests")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)


@pytest.fixture(params=[("David Bowie", "artist", "movie", 1), ("Spirited Away", "movie", "artist", 3)])
def captured_pair(request):
    name, source, target, first = request.param
    paths = [CAPTURES / f"request-{i}.json" for i in (first, first + 1)]
    if not all(p.is_file() for p in paths):
        pytest.skip("Actual private Qloo captures absent; no synthetic replacement")
    return name, source, target, *(json.loads(p.read_text()) for p in paths)


def test_actual_capture_decision_retains_ids_and_provenance(captured_pair):
    name, source, target, search, recs = captured_pair
    chapter, decision = build_decision(search, recs, name, source, target)
    seed = next(e for e in search["entities"] if e["name"] == name)
    assert decision["seed_id"] == seed["entity_id"]
    selected = next(e for e in recs["entities"] if e["entity_id"] == decision["target_id"])
    assert decision["target_name"] == selected["name"]
    assert decision["supporting_tag_id"] in {t.get("id") or t.get("tag_id") for t in selected["tags"]}
    assert decision["source_requests"] == [
        {k: record[k] for k in ("path", "params", "at_utc", "body_sha256")} for record in (search, recs)
    ]
    sera = next(o for loc in chapter.locations if loc.id == "archive" for o in loc.objects if o.id == "sera")
    assert all("culture_echo" in choice.requires for choice in sera.choices)


@pytest.mark.parametrize(
    "case",
    [
        "empty",
        "malformed",
        "wrong_category",
        "invalid_id",
        "unknown_category",
        "http_401",
        "http_429",
        "http_500",
        "timeout",
    ],
)
def test_prototype_rejects_synthetic_failures_not_live_provider_behavior(captured_pair, case):
    name, source, target, search, recs = copy.deepcopy(captured_pair)
    if case == "empty":
        recs["entities"] = []
    elif case == "malformed":
        recs["entities"] = "not an entity list"
    elif case == "wrong_category":
        for entity in recs["entities"]:
            entity["subtype"] = "urn:entity:brand"
    elif case == "invalid_id":
        for entity in recs["entities"]:
            entity["entity_id"] = "invalid"
    elif case == "unknown_category":
        target = "unknown"
    elif case.startswith("http_"):
        recs["http_status"] = int(case.split("_")[1])
    else:
        recs["http_status"] = None
        recs["cli_exit_code"] = None
        recs["outcome"] = "NETWORK_TLS_OR_TIMEOUT"
    with pytest.raises(ValueError):
        build_decision(search, recs, name, source, target)


def test_current_production_gate_preserves_progress_and_sanitizes_logs(tmp_path, caplog):
    config = Settings(
        database_url="sqlite:///" + str(tmp_path / "audit.sqlite3"), environment="test", requests_per_minute=1000
    )
    caplog.set_level(logging.INFO, logger="infinite_stories")
    with TestClient(create_app(config)) as client:
        response, headers, _ = start(client)
        view = choose(client, headers, response.json(), "mara", "take_map")
        session_url = "/v1/sessions/" + view["session_id"]

        def snapshot():
            with client.app.state.store.engine.connect() as connection:
                return [dict(x) for x in connection.execute(select(games)).mappings()], [
                    dict(x) for x in connection.execute(select(receipts)).mappings()
                ]

        before = snapshot()
        sentinel = "SYNTHETIC_SECRET_MUST_NOT_ECHO"
        body = {"request_id": str(uuid4()), "mode": "cultural", "interests": [{"name": sentinel, "category": "artist"}]}
        denied = client.post("/v1/sessions", headers=headers, json=body)
        assert denied.status_code == 503
        assert denied.json()["error"]["code"] == "QLOO_NOT_VERIFIED"
        assert snapshot() == before
        body["interests"][0]["category"] = "unknown"
        invalid = client.post("/v1/sessions", headers=headers, json=body)
        assert invalid.status_code == 422
        assert snapshot() == before
        assert client.get(session_url, headers=headers).json()["state"] == view["state"]
        assert client.get("/v1/capabilities").json()["cultural_generation"] is False
        with pytest.raises(DomainError, match="QLOO_NOT_VERIFIED"):
            CulturalProvider().generate([])
        assert sentinel not in denied.text + invalid.text + caplog.text
        assert headers["Authorization"] not in caplog.text
    with TestClient(create_app(config)) as restarted:
        loaded = restarted.get(session_url, headers=headers)
        assert loaded.status_code == 200
        assert loaded.json()["state"] == view["state"]


REMAINING = ROOT / "reports/local/qloo-remaining-categories-20261020"


def remaining_pair(name, category, first):
    paths = [REMAINING / f"request-{i}.json" for i in (first, first + 1)]
    if not all(p.is_file() for p in paths):
        pytest.skip("Actual remaining-category captures absent; no synthetic substitute")
    return name, category, *(json.loads(p.read_text()) for p in paths)


@pytest.mark.parametrize(
    "name,category,first",
    [("Dune", "book", 1), ("LEGO", "brand", 3), ("The Legend of Zelda: Breath of the Wild", "videogame", 5)],
)
def test_remaining_actual_seed_identity(name, category, first):
    _, _, search, _ = remaining_pair(name, category, first)
    candidates = seed_candidates(search, name, category)
    assert search["http_status"] == 200
    assert len(candidates) == 1
    assert "urn:entity:" + category in candidates[0]["types"]
    if category == "book":
        assert candidates[0]["disambiguation"] == "1965, Frank Herbert"
        assert candidates[0]["properties"]["publication_year"] == 1965


@pytest.mark.parametrize(
    "name,category,first",
    [("Dune", "book", 1), ("LEGO", "brand", 3), ("The Legend of Zelda: Breath of the Wild", "videogame", 5)],
)
def test_remaining_actual_outcome_is_not_replaced_by_mock_success(name, category, first):
    _, _, search, recs = remaining_pair(name, category, first)
    if category == "book":
        assert recs["http_status"] == 400 and recs["result_count"] is None
        with pytest.raises(ValueError):
            build_remaining_decision(search, recs, name, category, "movie")
        return
    chapter, decision = build_remaining_decision(search, recs, name, category, "movie")
    assert recs["http_status"] == 200 and recs["valid_distinct_result_count"] == 5
    assert decision["target_id"] in {e["entity_id"] for e in recs["entities"]}
    assert decision["seed_id"] == seed_candidates(search, name, category)[0]["entity_id"]
    assert decision["source_requests"][1]["body_sha256"] == recs["body_sha256"]
    proof = json.loads((REMAINING / f"decision-proof-{category}-to-movie.json").read_text())
    assert proof["status"] == "PASS" and len(proof["checks"]) == 8 and all(proof["checks"].values())
    assert proof["final_state"]["visits"] == 4
    assert any(
        "culture_echo" in choice.requires
        for loc in chapter.locations
        for obj in loc.objects
        if obj.id == "sera"
        for choice in obj.choices
    )


@pytest.mark.parametrize(
    "name,category,first", [("LEGO", "brand", 3), ("The Legend of Zelda: Breath of the Wild", "videogame", 5)]
)
@pytest.mark.parametrize("case", ["empty", "invalid", "unknown", "mismatch", "http429", "timeout"])
def test_remaining_synthetic_negative_records_are_rejected(name, category, first, case):
    _, _, search, recs = remaining_pair(name, category, first)
    if case == "empty":
        recs["entities"] = []
    elif case == "invalid":
        for e in recs["entities"]:
            e["entity_id"] = "invalid"
    elif case == "unknown":
        category = "unknown"
    elif case == "mismatch":
        recs["params"]["signal.interests.entities"] = "not-the-verified-seed"
    elif case == "http429":
        recs["http_status"] = 429
    else:
        recs["http_status"] = None
        recs["cli_exit_code"] = None
    with pytest.raises(ValueError):
        build_remaining_decision(search, recs, name, category, "movie")
