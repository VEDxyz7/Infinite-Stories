"""Offline cultural creation recovery; provider captures are never sent to Qloo."""

import os
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Event
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, select

from backend.app.main import create_app
from backend.app.models import NewGame
from backend.app.store import digest, games, generations, owner_digest, receipts
from backend.tests.test_cultural_production import captured, envelope, harness
from backend.tests.test_service import action, choose, start


@pytest.fixture(params=["sqlite", "postgres"])
def environment(tmp_path, request):
    config, provider, calls, interest, _ = harness(tmp_path, "artist")
    if request.param == "postgres":
        if not os.getenv("IS_TEST_POSTGRES_URL"):
            pytest.skip("Requires real disposable PostgreSQL; no substitute")
        config = replace(config, database_url=os.environ["IS_TEST_POSTGRES_URL"])
    headers = {"Authorization": "Bearer " + secrets.token_urlsafe(32)}
    body = {"request_id": str(uuid4()), "mode": "cultural", "interests": [interest]}
    return config, provider, calls, headers, body


def seed_pending(app, headers, body):
    request = NewGame.model_validate(body)
    with app.state.store.engine.begin() as connection:
        connection.execute(
            insert(generations).values(
                owner=owner_digest(headers["Authorization"][7:]),
                request_id=body["request_id"],
                payload_hash=digest(request.model_dump(mode="json", exclude_none=True)),
                status="pending",
                created=time.time() - 86400,
            )
        )


def recover(client, headers, body, previous=None):
    return client.post(
        "/v1/sessions/recover", headers=headers, json={"creation": body, "previous_session_id": previous}
    )


def test_exact_interrupted_creation_recovers_prior_progress_after_restart(environment):
    config, provider, calls, headers, body = environment
    with TestClient(create_app(config, cultural_provider=provider)) as client:
        created, _, _ = start(client, token=headers["Authorization"][7:])
        saved = choose(client, headers, created.json(), "mara", "take_map")
        seed_pending(client.app, headers, body)
        repeated = client.post("/v1/sessions", headers=headers, json=body)
        assert repeated.status_code == 409 and repeated.json()["error"]["code"] == "QLOO_GENERATION_PENDING"
    with TestClient(create_app(replace(config, qloo_calls_allowed=False, qloo_key=""))) as restarted:
        response = recover(restarted, headers, body, saved["session_id"])
        assert response.status_code == 200, response.text
        assert response.json()["state"] == saved["state"] and response.json()["revision"] == saved["revision"]
        replay = recover(restarted, headers, body, saved["session_id"])
        assert replay.status_code == 200 and replay.json()["state"] == saved["state"]
        assert len(calls) == 0
        with restarted.app.state.store.engine.connect() as connection:
            row = (
                connection.execute(select(generations).where(generations.c.request_id == body["request_id"]))
                .mappings()
                .one()
            )
            assert row["status"] == "failed"


def test_without_any_save_recovery_is_terminal_and_never_regenerates(environment):
    config, provider, calls, headers, body = environment
    with TestClient(create_app(config, cultural_provider=provider)) as client:
        seed_pending(client.app, headers, body)
        for _ in range(2):
            response = recover(client, headers, body)
            assert response.status_code == 409 and response.json()["error"]["code"] == "QLOO_GENERATION_INTERRUPTED"
        replay = client.post("/v1/sessions", headers=headers, json=body)
        assert replay.status_code == 409 and replay.json()["error"]["code"] == "QLOO_GENERATION_INTERRUPTED"
        assert len(calls) == 0


def test_recovery_after_response_loss_returns_created_run_not_old_save(environment):
    config, provider, calls, headers, body = environment
    with TestClient(create_app(config, cultural_provider=provider)) as client:
        old, _, _ = start(client, token=headers["Authorization"][7:])
        result = client.post("/v1/sessions", headers=headers, json=body)
        assert result.status_code == 200
        saved = choose(client, headers, result.json(), "mara", "take_map")
    with TestClient(create_app(replace(config, qloo_calls_allowed=False, qloo_key=""))) as restarted:
        response = recover(restarted, headers, body, old.json()["session_id"])
        assert response.status_code == 200, response.text
        assert response.json()["session_id"] == saved["session_id"]
        assert response.json()["state"] == saved["state"] and response.json()["revision"] == saved["revision"]
        assert len(calls) == 2


def test_recovery_before_creation_arrives_tombstones_without_provider(environment):
    config, provider, calls, headers, body = environment
    with TestClient(create_app(config, cultural_provider=provider)) as client:
        assert recover(client, headers, body).json()["error"]["code"] == "QLOO_GENERATION_INTERRUPTED"
        for _ in range(2):
            replay = client.post("/v1/sessions", headers=headers, json=body)
            assert replay.status_code == 409 and replay.json()["error"]["code"] == "QLOO_GENERATION_INTERRUPTED"
        assert len(calls) == 0
        with client.app.state.store.engine.connect() as connection:
            assert not connection.execute(
                select(games).where(games.c.owner == owner_digest(headers["Authorization"][7:]))
            ).first()


def test_recovery_ownership_payload_conflict_and_invalid_prior_do_not_leak_or_reset(environment):
    config, provider, calls, headers, body = environment
    with TestClient(create_app(config, cultural_provider=provider)) as client:
        created, _, _ = start(client, token=headers["Authorization"][7:])
        saved = choose(client, headers, created.json(), "mara", "take_map")
        seed_pending(client.app, headers, body)
        changed = {**body, "interests": [{"name": "Other artist", "category": "artist"}]}
        conflict = recover(client, headers, changed, saved["session_id"])
        assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
        stranger = {"Authorization": "Bearer " + secrets.token_urlsafe(32)}
        foreign = recover(client, stranger, body, saved["session_id"])
        assert foreign.status_code == 409 and foreign.json()["error"]["code"] == "QLOO_GENERATION_INTERRUPTED"
        with client.app.state.store.engine.connect() as connection:
            own = connection.execute(
                select(generations.c.status).where(
                    generations.c.owner == owner_digest(headers["Authorization"][7:]),
                    generations.c.request_id == body["request_id"],
                )
            ).scalar_one()
            assert own == "pending"
        assert recover(client, headers, body, str(uuid4())).status_code == 409
        restored = client.get("/v1/sessions/" + saved["session_id"], headers=headers).json()
        assert restored["state"] == saved["state"] and restored["revision"] == saved["revision"]
        assert len(calls) == 0


def test_concurrent_recovery_replays_preserve_quest_receipts_and_original_action_id(environment):
    config, provider, calls, headers, body = environment
    with TestClient(create_app(config, cultural_provider=provider)) as client:
        created, _, _ = start(client, token=headers["Authorization"][7:])
        before = created.json()
        request_id = str(uuid4())
        command = {"kind": "position", "x": 5, "y": 5}
        saved = action(client, headers, before, command, request_id).json()
        seed_pending(client.app, headers, body)
        with ThreadPoolExecutor(max_workers=4) as pool:
            replies = list(pool.map(lambda _: recover(client, headers, body, saved["session_id"]), range(4)))
        assert all(r.status_code == 200 for r in replies), [r.text for r in replies]
        assert all(r.json()["state"] == saved["state"] and r.json()["revision"] == saved["revision"] for r in replies)
        replayed = action(client, headers, before, command, request_id)
        assert replayed.status_code == 200 and replayed.json()["idempotent_replay"]
        assert replayed.json()["state"] == saved["state"] and replayed.json()["revision"] == saved["revision"]
        with client.app.state.store.engine.connect() as connection:
            assert len(connection.execute(select(receipts).where(receipts.c.game_id == saved["session_id"])).all()) == 1
            assert (
                len(
                    connection.execute(
                        select(games).where(games.c.owner == owner_digest(headers["Authorization"][7:]))
                    ).all()
                )
                == 1
            )
        assert len(calls) == 0


@pytest.mark.parametrize("fail", [False, True])
def test_cancellation_fences_late_worker_result_and_late_error(environment, fail):
    config, _, _, headers, body = environment
    _, search, recs, _ = captured("artist")
    entered, release = Event(), Event()

    def slow(request):
        if request.url.path == "/search":
            return httpx.Response(200, json=envelope(search))
        entered.set()
        assert release.wait(10), "Test must release the controlled provider"
        return httpx.Response(503 if fail else 200, json={"error": "synthetic outage"} if fail else envelope(recs))

    # Use the same selected database but an independently controlled MockTransport.
    from backend.app.providers import CulturalProvider

    provider = CulturalProvider(config, httpx.MockTransport(slow))
    with TestClient(create_app(config, cultural_provider=provider)) as client:
        old, _, _ = start(client, token=headers["Authorization"][7:])
        saved = choose(client, headers, old.json(), "mara", "take_map")
        with ThreadPoolExecutor(max_workers=2) as pool:
            writing = pool.submit(client.post, "/v1/sessions", headers=headers, json=body)
            try:
                assert entered.wait(10)
                response = recover(client, headers, body, saved["session_id"])
                assert response.status_code == 200 and response.json()["state"] == saved["state"]
            finally:
                release.set()
            result = writing.result(timeout=10)
            assert result.status_code == (503 if fail else 409)
        with client.app.state.store.engine.connect() as connection:
            row = (
                connection.execute(
                    select(generations).where(
                        generations.c.owner == owner_digest(headers["Authorization"][7:]),
                        generations.c.request_id == body["request_id"],
                    )
                )
                .mappings()
                .one()
            )
            assert row["error"]["code"] == "QLOO_GENERATION_INTERRUPTED"
            assert (
                len(
                    connection.execute(
                        select(games).where(games.c.owner == owner_digest(headers["Authorization"][7:]))
                    ).all()
                )
                == 1
            )
        assert recover(client, headers, body, saved["session_id"]).json()["state"] == saved["state"]


def test_failed_provider_before_save_can_recover_without_calling_it_again(environment):
    config, _, _, headers, body = environment
    seen = []

    def outage(request):
        seen.append(True)
        return httpx.Response(503, json={"error": "controlled outage"})

    from backend.app.providers import CulturalProvider

    provider = CulturalProvider(config, httpx.MockTransport(outage))
    with TestClient(create_app(config, cultural_provider=provider)) as client:
        failed = client.post("/v1/sessions", headers=headers, json=body)
        assert failed.status_code == 503
        for _ in range(2):
            assert recover(client, headers, body).json()["error"]["code"] == "QLOO_GENERATION_INTERRUPTED"
        assert len(seen) == 1
        # A new ID is explicit new-game intent, never implicit recovery.
        created = client.post("/v1/sessions", headers=headers, json={"request_id": str(uuid4()), "mode": "authored"})
        assert created.status_code == 200 and created.json()["state"]["cultural_context"] is None


def test_concurrent_completion_and_recovery_choose_one_atomic_outcome(environment):
    config, provider, _, headers, body = environment
    with TestClient(create_app(config, cultural_provider=provider)) as client:
        old, _, _ = start(client, token=headers["Authorization"][7:])
        prior = old.json()
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(client.post, "/v1/sessions", headers=headers, json=body)
            b = pool.submit(recover, client, headers, body, prior["session_id"])
            created, recovered = a.result(), b.result()
        assert recovered.status_code == 200
        assert created.status_code in (200, 409)
        final = recover(client, headers, body, prior["session_id"])
        assert final.status_code == 200 and final.json()["session_id"] == recovered.json()["session_id"]
        if created.status_code == 200:
            assert created.json()["session_id"] == recovered.json()["session_id"]
        else:
            assert recovered.json()["session_id"] == prior["session_id"]
        with client.app.state.store.engine.connect() as connection:
            mine = connection.execute(
                select(games).where(games.c.owner == owner_digest(headers["Authorization"][7:]))
            ).all()
            assert len(mine) == (2 if created.status_code == 200 else 1)


def _interrupted_process(config, body, headers, ready):
    """Spawn-only fixture worker. Blocks a mocked request outside any DB tx."""
    from backend.app.providers import CulturalProvider

    def blocked(request):
        from pathlib import Path

        Path(ready).write_text("ready")
        Event().wait(30)
        return httpx.Response(503, json={"error": "controlled interruption"})

    provider = CulturalProvider(config, httpx.MockTransport(blocked))
    with TestClient(create_app(config, cultural_provider=provider)) as client:
        client.post("/v1/sessions", headers=headers, json=body)


@pytest.mark.parametrize("with_save", [False, True])
def test_actual_worker_process_termination_and_restart_preserve_recovery(environment, with_save, tmp_path):
    import multiprocessing

    config, _, calls, headers, body = environment
    saved = None
    if with_save:
        with TestClient(create_app(config)) as client:
            created, _, _ = start(client, token=headers["Authorization"][7:])
            saved = choose(client, headers, created.json(), "mara", "take_map")
    context = multiprocessing.get_context("spawn")
    ready = tmp_path / "mock-provider-ready"
    worker = context.Process(target=_interrupted_process, args=(config, body, headers, str(ready)))
    worker.start()
    try:
        deadline = time.monotonic() + 15
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert ready.exists(), "Worker did not reach mocked provider request"
        worker.terminate()
        worker.join(10)
        assert not worker.is_alive() and worker.exitcode != 0
        # Fresh application/engine: neither providers nor process-local state recover it.
        with TestClient(create_app(replace(config, qloo_calls_allowed=False, qloo_key=""))) as restarted:
            result = recover(restarted, headers, body, saved["session_id"] if saved else None)
            if saved:
                assert result.status_code == 200 and result.json()["state"] == saved["state"]
                assert result.json()["revision"] == saved["revision"]
            else:
                assert result.status_code == 409 and result.json()["error"]["code"] == "QLOO_GENERATION_INTERRUPTED"
        with TestClient(create_app(replace(config, qloo_calls_allowed=False, qloo_key=""))) as again:
            repeated = recover(again, headers, body, saved["session_id"] if saved else None)
            assert repeated.status_code == result.status_code
            if saved:
                assert repeated.json()["state"] == saved["state"]
        assert len(calls) == 0
    finally:
        if worker.is_alive():
            worker.terminate()
        worker.join(10)


@pytest.mark.parametrize("invalid", ["expired", "checksum", "incomplete_evidence"])
def test_recovery_never_publishes_or_repairs_invalid_saved_state(environment, invalid):
    from sqlalchemy import update

    config, provider, calls, headers, body = environment
    with TestClient(create_app(config, cultural_provider=provider)) as client:
        created, _, _ = start(client, token=headers["Authorization"][7:])
        saved = created.json()
        change = {}
        if invalid == "expired":
            change = {"expires": time.time() - 1}
        elif invalid == "checksum":
            change = {"state_hash": "0" * 64}
        else:
            incomplete = {
                **saved["state"],
                "mode": "cultural",
                "cultural_source": "qloo",
                "cultural_context": {"links": []},
            }
            change = {"state": incomplete, "state_hash": digest(incomplete)}
        with client.app.state.store.engine.begin() as connection:
            connection.execute(update(games).where(games.c.id == saved["session_id"]).values(**change))
        response = recover(client, headers, body, saved["session_id"])
        assert response.status_code == 409 and response.json()["error"]["code"] == "QLOO_GENERATION_INTERRUPTED"
        assert "state" not in response.json() and len(calls) == 0
        with client.app.state.store.engine.connect() as connection:
            row = connection.execute(select(games).where(games.c.id == saved["session_id"])).mappings().one()
            for key, value in change.items():
                assert row[key] == value


def _interrupted_recovery_process(config, body, headers, previous, ready):
    from pathlib import Path

    from sqlalchemy import event

    with TestClient(create_app(replace(config, qloo_calls_allowed=False, qloo_key=""))) as client:

        @event.listens_for(client.app.state.store.engine, "commit")
        def pause_before_commit(connection):
            Path(ready).write_text("ready")
            Event().wait(30)

        recover(client, headers, body, previous)


def test_actual_restart_during_uncommitted_recovery_rolls_back_and_can_recover_again(environment, tmp_path):
    import multiprocessing

    config, provider, calls, headers, body = environment
    with TestClient(create_app(config, cultural_provider=provider)) as client:
        created, _, _ = start(client, token=headers["Authorization"][7:])
        saved = choose(client, headers, created.json(), "mara", "take_map")
        seed_pending(client.app, headers, body)
    ready = tmp_path / "recovery-before-commit"
    worker = multiprocessing.get_context("spawn").Process(
        target=_interrupted_recovery_process, args=(config, body, headers, saved["session_id"], str(ready))
    )
    worker.start()
    try:
        deadline = time.monotonic() + 15
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert ready.exists()
        worker.terminate()
        worker.join(10)
        assert not worker.is_alive()
        with TestClient(create_app(replace(config, qloo_calls_allowed=False, qloo_key=""))) as restarted:
            with restarted.app.state.store.engine.connect() as connection:
                status = connection.execute(
                    select(generations.c.status).where(
                        generations.c.owner == owner_digest(headers["Authorization"][7:]),
                        generations.c.request_id == body["request_id"],
                    )
                ).scalar_one()
                assert status == "pending", "Uncommitted cancellation must roll back on process exit"
            result = recover(restarted, headers, body, saved["session_id"])
            assert result.status_code == 200 and result.json()["state"] == saved["state"]
            assert result.json()["revision"] == saved["revision"]
            assert len(calls) == 0
    finally:
        if worker.is_alive():
            worker.terminate()
        worker.join(10)
