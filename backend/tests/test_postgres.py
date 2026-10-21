"""Optional real PostgreSQL integration. Never substitutes SQLite or a mock."""

import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.tests.test_service import action, choose, start, visit_next

pytestmark = pytest.mark.skipif(
    not os.getenv("IS_TEST_POSTGRES_URL"), reason="Real disposable PostgreSQL service not configured"
)


def test_real_postgres_persistence_idempotency():
    url = os.environ["IS_TEST_POSTGRES_URL"]
    if not url.startswith("postgresql+psycopg://"):
        pytest.fail("This test requires real PostgreSQL, never a substitute")
    config = Settings(database_url=url, environment="test")
    headers = {"Authorization": "Bearer " + secrets.token_urlsafe(32)}
    with TestClient(create_app(config)) as client:
        result = client.post("/v1/sessions", headers=headers, json={"request_id": str(uuid4()), "mode": "authored"})
        assert result.status_code == 200
        view = result.json()
        body = {"request_id": str(uuid4()), "expected_revision": 0, "command": {"kind": "position", "x": 5, "y": 5}}
        action = "/v1/sessions/" + view["session_id"] + "/actions"
        assert client.post(action, headers=headers, json=body).status_code == 200
        assert client.post(action, headers=headers, json=body).json()["idempotent_replay"] is True
    with TestClient(create_app(config)) as restarted:
        restored = restarted.get("/v1/sessions/" + view["session_id"], headers=headers)
        assert restored.status_code == 200
        assert restored.json()["revision"] == 1
        assert restarted.delete("/v1/sessions/" + view["session_id"], headers=headers).status_code == 200


@pytest.mark.parametrize("ending,choice", [("together", "light_together"), ("keeper", "leave_keeper")])
def test_real_postgres_complete_chapter_and_json_state_survive_restart(ending, choice):
    config = Settings(database_url=os.environ["IS_TEST_POSTGRES_URL"], environment="test", requests_per_minute=1000)
    with TestClient(create_app(config)) as client:
        response, headers, _ = start(client)
        assert response.status_code == 200
        view = choose(client, headers, response.json(), "mara", "take_map")
        view = choose(client, headers, visit_next(client, headers, view), "ivo", "learn_rhythm")
        view = choose(client, headers, visit_next(client, headers, view), "sera", "promise_guard")
        view = choose(client, headers, visit_next(client, headers, view), "beacon", choice)
        assert view["state"]["ending"] == ending and view["state"]["visits"] == 4
    with TestClient(create_app(config)) as restarted:
        restored = restarted.get("/v1/sessions/" + view["session_id"], headers=headers)
        assert restored.status_code == 200
        assert restored.json()["state"] == view["state"]
        assert restarted.delete("/v1/sessions/" + view["session_id"], headers=headers).status_code == 200


def test_real_postgres_concurrent_duplicate_has_one_committed_revision():
    config = Settings(database_url=os.environ["IS_TEST_POSTGRES_URL"], environment="test")
    with TestClient(create_app(config)) as client:
        response, headers, _ = start(client)
        assert response.status_code == 200
        view, rid = response.json(), str(uuid4())
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(lambda _: action(client, headers, view, {"kind": "position", "x": 5, "y": 5}, rid), range(2))
            )
        assert all(result.status_code in (200, 409) for result in results)
        saved = client.get("/v1/sessions/" + view["session_id"], headers=headers)
        assert saved.status_code == 200 and saved.json()["revision"] == 1
        assert action(client, headers, view, {"kind": "position", "x": 5, "y": 5}, rid).json()["idempotent_replay"]
        assert client.delete("/v1/sessions/" + view["session_id"], headers=headers).status_code == 200
