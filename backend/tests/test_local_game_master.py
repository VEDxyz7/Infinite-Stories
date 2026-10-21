"""Controlled local HTTP doubles; these are not actual model evaluations."""

import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.content import make_chapter
from backend.app.engine import game_view
from backend.app.local_game_master import OllamaGameMaster
from backend.app.main import create_app
from backend.app.models import DomainError, GameState
from backend.tests.test_service import move, start


def settings(**kw):
    return Settings(llm_provider="ollama", llm_model="qwen3:4b", llm_calls_allowed=True, **kw)


def response(action=None, narrative="The lanterns shimmer. Progress is unchanged."):
    action_id = "none" if action is None else action.get("kind", "") + ":" + action.get("target", "")
    if action and action.get("kind") == "choose":
        action_id += ":" + action.get("choice", "")
    return {
        "done": True,
        "done_reason": "stop",
        "message": {
            "content": json.dumps(
                {
                    "action_id": action_id,
                    "narrative": narrative,
                }
            )
        },
    }


def plan_response(tool="propose_gameplay"):
    return {"done": True, "done_reason": "stop", "message": {"content": json.dumps({"tool_id": tool})}}


def is_plan(request):
    return "tool_id" in json.loads(request.content)["format"]["properties"]


@pytest.mark.parametrize(
    "status,code",
    [
        (400, "MODEL_UPSTREAM_ERROR"),
        (401, "MODEL_AUTH_ERROR"),
        (403, "MODEL_AUTH_ERROR"),
        (429, "MODEL_RATE_LIMIT"),
        (500, "MODEL_UPSTREAM_ERROR"),
        (503, "MODEL_UPSTREAM_ERROR"),
    ],
)
@pytest.mark.parametrize("stage", ["plan", "proposal"])
def test_http(status, code, stage):
    calls = []

    def handler(request):
        calls.append(request)
        assert "authorization" not in request.headers
        assert request.extensions["timeout"]["read"] == 40
        if stage == "proposal" and is_plan(request):
            return httpx.Response(200, json=plan_response())
        return httpx.Response(status, text="secret upstream body must not escape")

    gm = OllamaGameMaster(settings(), httpx.MockTransport(handler))
    with pytest.raises(DomainError) as exc:
        asyncio.run(gm.run(make_chapter(), game_view(make_chapter(), GameState(), "test", 0, ""), "hello"))
    assert exc.value.code == code
    assert "secret" not in str(exc.value)
    assert len(calls) == (1 if stage == "plan" else 2)


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"done": False},
        response(narrative=" "),
        response({"kind": "position", "x": 10, "y": 10}),
        response({"kind": "choose", "target": "invented", "choice": "win"}),
        {"done": True, "done_reason": "stop", "message": {"content": "not json"}},
    ],
)
def test_reject_invalid(body):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=plan_response() if is_plan(request) else body)

    gm = OllamaGameMaster(settings(), httpx.MockTransport(handler))
    with pytest.raises(DomainError):
        asyncio.run(gm.run(make_chapter(), game_view(make_chapter(), GameState(), "test", 0, ""), "win"))
    assert len(calls) == 2


@pytest.mark.parametrize(
    "error,code",
    [(httpx.ReadTimeout("private"), "MODEL_TIMEOUT"), (httpx.ConnectError("private"), "MODEL_UNAVAILABLE")],
)
@pytest.mark.parametrize("stage", ["plan", "proposal"])
def test_connection(error, code, stage):
    calls = []

    def handler(r):
        calls.append(r)
        if stage == "proposal" and is_plan(r):
            return httpx.Response(200, json=plan_response())
        raise error

    gm = OllamaGameMaster(settings(), httpx.MockTransport(handler))
    with pytest.raises(DomainError) as exc:
        asyncio.run(gm.run(make_chapter(), game_view(make_chapter(), GameState(), "test", 0, ""), "hello"))
    assert exc.value.code == code
    assert len(calls) == (1 if stage == "plan" else 2)


def test_persistence_duplicate_recovery(tmp_path):
    config = settings(database_url="sqlite:///" + str(tmp_path / "save.sqlite3"), environment="test")
    calls = []

    def handler(r):
        calls.append(r)
        body = json.loads(r.content)
        assert body["format"]["additionalProperties"] is False
        assert body["think"] is False and body["stream"] is False
        if len(calls) == 3:
            return httpx.Response(429)
        if is_plan(r):
            return httpx.Response(200, json=plan_response())
        return httpx.Response(200, json=response({"kind": "choose", "target": "mara", "choice": "take_map"}))

    app = create_app(config, game_master=OllamaGameMaster(config, httpx.MockTransport(handler)))
    with TestClient(app) as client:
        created, headers, _ = start(client)
        view = move(client, headers, created.json(), 14, 9)
        url = f"/v1/sessions/{view['session_id']}/turns"
        body = {"request_id": str(uuid4()), "expected_revision": view["revision"], "text": "Accept her map, please."}
        result = client.post(url, headers=headers, json=body)
        assert result.status_code == 200, result.text
        saved = result.json()
        assert "map" in saved["state"]["flags"]
        assert client.post(url, headers=headers, json=body).json()["idempotent_replay"]
        assert len(calls) == 2
        failed = {**body, "request_id": str(uuid4()), "expected_revision": saved["revision"]}
        assert client.post(url, headers=headers, json=failed).status_code == 503
        assert client.post(url, headers=headers, json=failed).status_code == 503
        assert len(calls) == 3
    with TestClient(create_app(config)) as client:
        resumed = client.get(url.removesuffix("/turns"), headers=headers).json()
        assert resumed["state"] == saved["state"] and resumed["revision"] == saved["revision"]


def test_local_security_configuration():
    settings().validate()
    with pytest.raises(ValueError):
        settings(llm_base_url="https://example.com").validate()
    with pytest.raises(ValueError):
        Settings(llm_provider="ollama", llm_model="qwen3:cloud").validate()


def test_saved_dialogue_reaches_next_turn_after_restart(tmp_path):
    config = settings(database_url="sqlite:///" + str(tmp_path / "dialogue.sqlite3"), environment="test")
    captured = []

    def handler(request):
        captured.append(json.loads(request.content))
        if is_plan(request):
            return httpx.Response(200, json=plan_response())
        return httpx.Response(200, json=response(narrative="Mara waits beside the copper lamp. Progress is unchanged."))

    gm = OllamaGameMaster(config, httpx.MockTransport(handler))
    with TestClient(create_app(config, game_master=gm)) as client:
        created, headers, _ = start(client)
        view = created.json()
        url = "/v1/sessions/" + view["session_id"] + "/turns"
        body = {"request_id": str(uuid4()), "expected_revision": view["revision"], "text": "Describe the light."}
        result = client.post(url, headers=headers, json=body)
        assert result.status_code == 200
        assert result.json()["state"] == view["state"]
    with TestClient(create_app(config, game_master=gm)) as client:
        body = {**body, "request_id": str(uuid4()), "text": "Tell me more about that lamp."}
        assert client.post(url, headers=headers, json=body).status_code == 200
        context = json.loads(captured[-1]["messages"][-1]["content"])["context"]
        assert context["recent_dialogue"] == ["Mara waits beside the copper lamp. Progress is unchanged."]
        assert (
            client.post(url, headers=headers, json={**body, "request_id": str(uuid4()), "text": "x" * 1001}).status_code
            == 422
        )
        assert len(captured) == 4


@pytest.mark.parametrize("category", ["artist", "movie", "brand", "videogame"])
def test_actual_cultural_projection_and_provenance(tmp_path, category):
    from backend.tests.test_cultural_production import harness

    cfg, provider, _, interest, _ = harness(tmp_path, category)
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        if is_plan(request):
            return httpx.Response(200, json=plan_response())
        return httpx.Response(200, json=response())

    gm = OllamaGameMaster(settings(), httpx.MockTransport(handler))
    with TestClient(create_app(cfg, cultural_provider=provider)) as client:
        created, _, _ = start(client, mode="authored")
        from backend.app.models import NewGame

        context = provider.generate(NewGame(request_id=uuid4(), mode="cultural", interests=[interest]).interests)
        # The production provider normalization above uses only historical capture replay.
        view = created.json()
        view["state"].update(mode="cultural", cultural_source="qloo", cultural_context=context.model_dump(mode="json"))
        asyncio.run(gm.run(make_chapter(), view, "What cultural evidence shapes this place?"))
    evidence = json.loads(seen[1]["messages"][1]["content"])["context"]["cultural_evidence"][0]
    assert evidence["provider_fact"]["seed"]["category"] == category
    assert evidence["provider_fact"]["recommendation"]["id"] == str(context.links[0].selected_id)
    assert evidence["provider_fact"]["provenance"][0]["path"] == "/search"
    assert evidence["original_story_interpretation"]["setting"] == context.links[0].setting


def test_schema_only_contains_engine_eligible_actions():
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        if is_plan(request):
            return httpx.Response(200, json=plan_response())
        return httpx.Response(200, json=response())

    gm = OllamaGameMaster(settings(), httpx.MockTransport(handler))
    chapter = make_chapter()
    state = GameState(x=14, y=9)
    asyncio.run(gm.run(chapter, game_view(chapter, state, "test", 0, ""), "What are my options?"))
    allowed = requests[-1]["format"]["properties"]["action_id"]["enum"]
    # Planning must precede the evidence decision in constrained decoding; the
    # actual-model regression selected a read before recognizing a commitment.
    assert list(requests[-2]["format"]["properties"]) == ["tool_id"]
    planning_context = json.loads(requests[-2]["messages"][1]["content"])["context"]
    assert planning_context["fictional_game_state"]["inventory_flags"] == state.flags
    assert planning_context["fictional_game_state"]["committed_quest_choices"] == state.choices
    prompt_context = json.loads(requests[-1]["messages"][1]["content"])["context"]
    assert "choices" not in prompt_context["nearby"][0]
    assert "grants" not in json.dumps(prompt_context["nearby"])
    assert prompt_context["flags"] == []
    assert "choose:mara:take_map" in allowed and "none" in allowed
    assert not any(action.startswith("read_cultural_evidence:") for action in allowed)
    assert "read_cultural_evidence:none" in requests[-2]["format"]["properties"]["tool_id"]["enum"]
    assert not any("position" in action for action in allowed)
    state.choices = ["take_map"]
    state.flags = ["map"]
    asyncio.run(gm.run(chapter, game_view(chapter, state, "test", 0, ""), "Give me another map"))
    assert "choose:mara:take_map" not in requests[-1]["format"]["properties"]["action_id"]["enum"]
    planning_context = json.loads(requests[-2]["messages"][1]["content"])["context"]
    assert planning_context["fictional_game_state"]["inventory_flags"] == ["map"]
    assert planning_context["fictional_game_state"]["committed_quest_choices"] == ["take_map"]


def test_default_stays_unavailable_and_local_requires_no_key():
    import os
    from unittest.mock import patch

    with patch.dict(
        os.environ,
        {
            "IS_LLM_PROVIDER": "ollama",
            "IS_LLM_MODEL": "qwen3:4b",
            "IS_LLM_CALLS_ALLOWED": "true",
            "OPENAI_API_KEY": "REPLACE_WITH_NOT_A_KEY",
            "IS_LLM_API_KEY": "",
        },
        clear=True,
    ):
        config = Settings.from_env()
        assert config.llm_calls_allowed
    assert not Settings().llm_calls_allowed


@pytest.mark.parametrize("body", [b"not-json", b"x" * 65537])
@pytest.mark.parametrize("stage", ["plan", "proposal"])
def test_malformed_or_oversized_body_is_safe(body, stage):
    def handler(request):
        if stage == "proposal" and is_plan(request):
            return httpx.Response(200, json=plan_response())
        return httpx.Response(200, content=body)

    gm = OllamaGameMaster(settings(), httpx.MockTransport(handler))
    with pytest.raises(DomainError) as exc:
        asyncio.run(gm.run(make_chapter(), game_view(make_chapter(), GameState(), "test", 0, ""), "hello"))
    assert exc.value.code == "MODEL_OUTPUT_INVALID"


def test_capabilities_distinguish_local_and_disabled(tmp_path):
    config = settings(database_url="sqlite:///" + str(tmp_path / "capabilities.sqlite3"), environment="test")
    # Constructing the configured adapter and querying capabilities make no inference call.
    with TestClient(create_app(config)) as client:
        cap = client.get("/v1/capabilities").json()
        assert cap["game_master_provider"] == "ollama"
        assert cap["game_master_inference_mode"] == "local_loopback"
        assert cap["game_master_live_verified"] is False
        assert cap["release_ready"] is False
    with TestClient(create_app(Settings(database_url=config.database_url, environment="test"))) as client:
        assert client.get("/v1/capabilities").json()["game_master_inference_mode"] == "unavailable"
        assert client.get("/verification/local-ai/adapter").status_code == 404


def test_explicit_local_replay_factory(monkeypatch, tmp_path):
    from scripts.local_ai_verification import create_local_ai_app

    monkeypatch.delenv("IS_LOCAL_AI_VERIFICATION", raising=False)
    with pytest.raises(RuntimeError):
        create_local_ai_app()
    monkeypatch.setenv("IS_LOCAL_AI_VERIFICATION", "1")
    monkeypatch.setenv("IS_LOCAL_MODEL_TAG", "qwen3:4b")
    monkeypatch.setenv("IS_CAPTURE_REPLAY_ONLY", "1")
    monkeypatch.setenv("IS_CAPTURE_REPLAY_DIRECTORY", str(tmp_path / "local-ai"))
    with TestClient(create_local_ai_app()) as client:
        cap = client.get("/v1/capabilities").json()
        assert cap["verification_mode"] == "captured_response_replay"
        assert cap["game_master_inference_mode"] == "local_loopback"
        diagnostic = client.get("/verification/local-ai/adapter").json()
        import hashlib
        import marshal

        from backend.app import local_game_master

        assert diagnostic["protocol"] == "ollama-typed-tool-plan-v1"
        assert diagnostic["planner_fields"] == ["tool_id"]
        assert (
            diagnostic["loaded_method_sha256"]["run"]
            == hashlib.sha256(marshal.dumps(local_game_master.OllamaGameMaster.run.__code__)).hexdigest()
        )
        assert diagnostic["latest_turn_inference_requests"] is None
        assert "/verification/local-ai/adapter" not in client.get("/openapi.json").json()["paths"]


def test_concurrent_local_turn_is_rejected_without_second_upstream_call():
    calls = []

    async def exercise():
        started = asyncio.Event()
        release = asyncio.Event()

        async def handler(request):
            calls.append(request)
            started.set()
            await release.wait()
            if is_plan(request):
                return httpx.Response(200, json=plan_response())
            return httpx.Response(200, json=response())

        gm = OllamaGameMaster(settings(), httpx.MockTransport(handler))
        view = game_view(make_chapter(), GameState(), "test", 0, "")
        first = asyncio.create_task(gm.run(make_chapter(), view, "hello"))
        await started.wait()
        with pytest.raises(DomainError) as exc:
            await gm.run(make_chapter(), view, "hello again")
        assert exc.value.code == "MODEL_BUSY"
        release.set()
        await first
        assert len(calls) == 2
        # The slot is released even after completion.
        await gm.run(make_chapter(), view, "hello once more")
        assert len(calls) == 4

    asyncio.run(exercise())


@pytest.mark.parametrize("failure_stage", ["plan", "proposal"])
def test_outage_recovery_new_turn_preserves_terminal_receipt(tmp_path, failure_stage):
    config = settings(database_url="sqlite:///" + str(tmp_path / "recovery.sqlite3"), environment="test")
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == (1 if failure_stage == "plan" else 2):
            raise httpx.ConnectError("private network detail", request=request)
        if is_plan(request):
            return httpx.Response(200, json=plan_response())
        return httpx.Response(200, json=response({"kind": "choose", "target": "mara", "choice": "take_map"}))

    def app():
        return create_app(config, game_master=OllamaGameMaster(config, httpx.MockTransport(handler)))

    with TestClient(app()) as client:
        created, headers, _ = start(client)
        view = move(client, headers, created.json(), 14, 9)
        url = "/v1/sessions/" + view["session_id"]
        body = {"request_id": str(uuid4()), "expected_revision": view["revision"], "text": "I accept the map."}
        failure = client.post(url + "/turns", headers=headers, json=body)
        assert failure.status_code == 503 and "private network detail" not in failure.text
        assert client.get(url, headers=headers).json()["state"] == view["state"]
    with TestClient(app()) as client:
        assert client.post(url + "/turns", headers=headers, json=body).status_code == 503
        failed_requests = 1 if failure_stage == "plan" else 2
        assert len(calls) == failed_requests  # A restarted backend never retries either stage of a failed ID.
        healthy = client.post(url + "/turns", headers=headers, json={**body, "request_id": str(uuid4())})
        assert healthy.status_code == 200, healthy.text
        assert healthy.json()["revision"] == view["revision"] + 1
        assert healthy.json()["state"]["choices"].count("take_map") == 1
        assert len(calls) == failed_requests + 2


def test_configuration_repr_redacts_server_keys():
    config = Settings(qloo_key="SYNTHETIC_QLOO_SECRET", llm_key="SYNTHETIC_MODEL_SECRET")
    assert "SYNTHETIC_" not in repr(config)


@pytest.mark.parametrize("category", ["artist", "movie", "brand", "videogame"])
@pytest.mark.parametrize("database", ["sqlite", "postgres"])
def test_cultural_fact_tool_is_authoritative_read_only_and_replayable(tmp_path, category, database):
    from backend.tests.test_cultural_production import harness

    cfg, provider, _, interest, _ = harness(tmp_path, category)
    if database == "postgres":
        import os
        from dataclasses import replace

        if not os.getenv("IS_TEST_POSTGRES_URL"):
            pytest.skip("Requires disposable PostgreSQL; no substitute")
        cfg = replace(cfg, database_url=os.environ["IS_TEST_POSTGRES_URL"])
    calls = []

    def handler(request):
        calls.append(request)
        body = json.loads(request.content)
        assert "read_cultural_evidence:0" in body["format"]["properties"]["tool_id"]["enum"]
        assert "action_id" not in body["format"]["properties"]
        return httpx.Response(200, json=plan_response("read_cultural_evidence:0"))

    gm = OllamaGameMaster(settings(), httpx.MockTransport(handler))
    import secrets

    headers = {"Authorization": "Bearer " + secrets.token_urlsafe(32)}
    with TestClient(create_app(cfg, game_master=gm, cultural_provider=provider)) as client:
        created = client.post(
            "/v1/sessions",
            headers=headers,
            json={"mode": "cultural", "request_id": str(uuid4()), "interests": [interest]},
        )
        assert created.status_code == 200
        before = created.json()
        url = "/v1/sessions/" + before["session_id"] + "/turns"
        body = {
            "request_id": str(uuid4()),
            "expected_revision": before["revision"],
            "text": "Explain the verified cultural evidence without changing anything.",
        }
        result = client.post(url, headers=headers, json=body)
        assert result.status_code == 200, result.text
        saved = result.json()
        assert saved["narrative_source"] == "cultural_evidence_tool"
        assert saved["narrative"].startswith("Saved Qloo evidence (server-rendered):")
        assert interest["name"] in saved["narrative"] or category == "brand" and "The Lego Group" in saved["narrative"]
        assert "Untrusted model prose" not in saved["narrative"]
        assert saved["state"] == before["state"] and saved["revision"] == before["revision"]
    with TestClient(create_app(cfg, game_master=gm, cultural_provider=provider)) as client:
        replay = client.post(url, headers=headers, json=body).json()
        assert replay["idempotent_replay"] and replay["narrative_source"] == "cultural_evidence_tool"
        assert len(calls) == 1


def test_raw_model_cannot_claim_provider_factual_attribution():
    def handler(request):
        return httpx.Response(
            200, json=plan_response() if is_plan(request) else response(narrative="Qloo proves you are an introvert.")
        )

    gm = OllamaGameMaster(
        settings(),
        httpx.MockTransport(handler),
    )
    with pytest.raises(DomainError) as exc:
        asyncio.run(gm.run(make_chapter(), game_view(make_chapter(), GameState(), "test", 0, ""), "infer personality"))
    assert exc.value.code == "MODEL_EVIDENCE_TOOL_REQUIRED"


@pytest.mark.parametrize(
    "tool,action",
    [
        ("read_cultural_evidence:unknown", None),
        ("read_cultural_evidence:none", {"kind": "choose", "target": "mara", "choice": "take_map"}),
        ("not_needed", {"kind": "read_cultural_evidence", "target": "none"}),
    ],
)
def test_read_tool_cannot_invent_target_or_combine_with_world_change(tool, action):
    body = plan_response(tool)
    proposal = json.loads(body["message"]["content"])
    if action:
        proposal["action_id"] = action
    body["message"]["content"] = json.dumps(proposal)
    gm = OllamaGameMaster(settings(), httpx.MockTransport(lambda r: httpx.Response(200, json=body)))
    state = GameState(x=14, y=9)
    with pytest.raises(DomainError) as exc:
        asyncio.run(gm.run(make_chapter(), game_view(make_chapter(), state, "test", 0, ""), "Read facts"))
    assert exc.value.code == "MODEL_OUTPUT_INVALID"
    assert state.flags == [] and state.choices == []


def test_authored_evidence_abstains_instead_of_fabricating():
    from backend.app.models import CulturalEvidenceReply

    body = plan_response("read_cultural_evidence:none")
    gm = OllamaGameMaster(settings(), httpx.MockTransport(lambda r: httpx.Response(200, json=body)))
    reply = asyncio.run(gm.run(make_chapter(), game_view(make_chapter(), GameState(), "test", 0, ""), "Read facts"))
    assert isinstance(reply, CulturalEvidenceReply) and reply.proposal is None
    assert "no Qloo cultural evidence" in reply.narrative


@pytest.mark.parametrize("field", ["tool_id", "action_id", "narrative"])
def test_required_planning_fields_cannot_be_omitted(field):
    body = plan_response() if field == "tool_id" else response()
    proposal = json.loads(body["message"]["content"])
    del proposal[field]
    body["message"]["content"] = json.dumps(proposal)

    def handler(request):
        return httpx.Response(200, json=plan_response() if field != "tool_id" and is_plan(request) else body)

    gm = OllamaGameMaster(settings(), httpx.MockTransport(handler))
    with pytest.raises(DomainError) as exc:
        asyncio.run(gm.run(make_chapter(), game_view(make_chapter(), GameState(), "test", 0, ""), "hello"))
    assert exc.value.code == "MODEL_OUTPUT_INVALID"


def test_planner_cannot_emit_unvalidated_factual_prose():
    body = plan_response("read_cultural_evidence:none")
    body["message"]["content"] = json.dumps(
        {"tool_id": "read_cultural_evidence:none", "intent": "Unvalidated factual claim"}
    )
    gm = OllamaGameMaster(settings(), httpx.MockTransport(lambda r: httpx.Response(200, json=body)))
    with pytest.raises(DomainError) as exc:
        asyncio.run(gm.run(make_chapter(), game_view(make_chapter(), GameState(), "test", 0, ""), "Read facts"))
    assert exc.value.code == "MODEL_OUTPUT_INVALID"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("The map remains unacquired; your inventory is empty.", True),
        ("No, you already have the first memory.", False),
        ("No, you have the map.", False),
        ("You do not yet possess the map.", True),
        ("The map remains with Mara.", True),
    ],
)
def test_inventory_evaluation_recognizes_actual_status_not_just_negation(text, expected):
    from scripts.evaluate_local_game_master import declares_map_unacquired

    assert declares_map_unacquired(text) is expected
