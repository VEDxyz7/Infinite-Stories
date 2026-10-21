"""Controlled upstream failures against saved cultural worlds. No live providers."""

from dataclasses import replace
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.providers import CulturalProvider
from backend.tests.test_cultural_production import captured, envelope, harness
from backend.tests.test_service import choose

CASES = [
    ("400", "QLOO_REQUEST_REJECTED"),
    ("401", "QLOO_AUTH"),
    ("403", "QLOO_AUTH"),
    ("429", "QLOO_RATE_LIMIT"),
    ("503", "QLOO_UPSTREAM"),
    ("network", "QLOO_NETWORK"),
    ("timeout", "QLOO_TIMEOUT"),
    ("malformed", "QLOO_RESPONSE_INVALID"),
    ("empty", "QLOO_EMPTY"),
    ("unresolved", "QLOO_UNRESOLVED"),
]


@pytest.mark.parametrize("case,expected", CASES)
@pytest.mark.parametrize("category", ["artist", "movie", "brand", "videogame"])
def test_failed_creation_preserves_cultural_progress_across_restart_and_recovers(
    tmp_path, case, expected, caplog, category
):
    _, search, recommendations, _ = captured(category)
    fault = [None]
    calls = []

    def controlled(request):
        calls.append(request.url.path)
        if fault[0] is not None:
            if case.isdigit():
                return httpx.Response(int(case), json={"error": "PRIVATE_UPSTREAM_SENTINEL"})
            if case == "network":
                raise httpx.ConnectError("PRIVATE_UPSTREAM_SENTINEL", request=request)
            if case == "timeout":
                raise httpx.ReadTimeout("PRIVATE_UPSTREAM_SENTINEL", request=request)
            if case == "malformed":
                return httpx.Response(200, content=b"PRIVATE_UPSTREAM_SENTINEL")
            if case == "empty":
                return httpx.Response(200, json={"results": []})
            return httpx.Response(404, json={"error": "PRIVATE_UPSTREAM_SENTINEL"})
        return httpx.Response(200, json=envelope(search if request.url.path == "/search" else recommendations))

    config, provider, _, interest, _ = harness(tmp_path, category, controlled, qloo_cache_seconds=0)
    headers = {"Authorization": "Bearer SYNTHETIC_TEST_GUEST_" + "x" * 43}
    body = {"request_id": str(uuid4()), "mode": "cultural", "interests": [interest]}
    with TestClient(create_app(config, cultural_provider=provider)) as client:
        created = client.post("/v1/sessions", headers=headers, json=body)
        assert created.status_code == 200
        prior = choose(client, headers, created.json(), "mara", "take_map")
        fault[0] = case
        failed = {**body, "request_id": str(uuid4())}
        response = client.post("/v1/sessions", headers=headers, json=failed)
        assert response.json()["error"]["code"] == expected
        count = len(calls)
        replay = client.post("/v1/sessions", headers=headers, json=failed)
        assert replay.json()["error"]["code"] == expected and len(calls) == count
        assert "PRIVATE_UPSTREAM_SENTINEL" not in response.text + replay.text + caplog.text
        loaded = client.get("/v1/sessions/" + prior["session_id"], headers=headers).json()
        assert loaded["state"] == prior["state"] and loaded["revision"] == prior["revision"]
    # Actual app/store restart over the same on-disk DB with provider disabled.
    with TestClient(create_app(replace(config, qloo_calls_allowed=False, qloo_key=""))) as client:
        loaded = client.get("/v1/sessions/" + prior["session_id"], headers=headers).json()
        assert loaded["state"] == prior["state"] and loaded["revision"] == prior["revision"]
    fault[0] = None
    restored = CulturalProvider(config, httpx.MockTransport(controlled))
    with TestClient(create_app(config, cultural_provider=restored)) as client:
        # Failed receipt remains terminal after recovery, never silently reissued.
        assert client.post("/v1/sessions", headers=headers, json=failed).json()["error"]["code"] == expected
        assert len(calls) == count
        good = client.post("/v1/sessions", headers=headers, json={**body, "request_id": str(uuid4())})
        assert good.status_code == 200 and len(calls) == count + 2
        loaded = client.get("/v1/sessions/" + prior["session_id"], headers=headers).json()
        assert loaded["state"] == prior["state"] and loaded["revision"] == prior["revision"]
        assert good.json()["session_id"] != prior["session_id"]


def test_production_factory_does_not_silently_enable_replay_or_accept_authoritative_state(tmp_path, monkeypatch):
    from backend.app.config import Settings

    monkeypatch.setenv("IS_CAPTURE_REPLAY_ONLY", "1")
    config = Settings(database_url="sqlite:///" + str(tmp_path / "real-factory.sqlite3"), environment="test")
    headers = {"Authorization": "Bearer SYNTHETIC_TEST_GUEST_" + "x" * 43}
    with TestClient(create_app(config)) as client:
        capabilities = client.get("/v1/capabilities").json()
        assert capabilities["verification_mode"] == ""
        assert capabilities["cultural_generation"] is False
        assert capabilities["qloo_adapter_live_verified"] is False
        body = {
            "request_id": str(uuid4()),
            "mode": "cultural",
            "interests": [{"name": "David Bowie", "category": "artist"}],
        }
        disabled = client.post("/v1/sessions", headers=headers, json=body)
        assert disabled.json()["error"]["code"] == "QLOO_NOT_VERIFIED"
        injection = client.post(
            "/v1/sessions", headers=headers, json={**body, "state": {"flags": ["culture_0"], "ending": "together"}}
        )
        assert injection.status_code == 422
