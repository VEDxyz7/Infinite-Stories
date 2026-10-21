"""Explicit loopback-only verification server: captured Qloo HTTP replay, never live.

Run only with IS_CAPTURE_REPLAY_ONLY=1. Production never imports this module.
No .env is loaded and no configured provider key is read.
"""

import os
from pathlib import Path

import httpx
from starlette.responses import Response

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.providers import CulturalProvider
from backend.tests.test_cultural_production import PAIRS, captured, envelope


def create_verification_app():
    if os.getenv("IS_CAPTURE_REPLAY_ONLY") != "1":
        raise RuntimeError("Explicit captured-response verification opt-in required")
    root = Path(__file__).resolve().parents[1]
    folder = Path(os.getenv("IS_CAPTURE_REPLAY_DIRECTORY", str(root / "reports/local/client-cultural-verification")))
    fault = os.getenv("IS_CAPTURE_REPLAY_FAULT", "")
    fault_file = os.getenv("IS_CAPTURE_REPLAY_FAULT_FILE", "")

    def scenario():
        value = Path(fault_file).read_text().strip() if fault_file else fault
        if value not in (
            "",
            "400",
            "401",
            "403",
            "429",
            "503",
            "network",
            "timeout",
            "malformed",
            "empty",
            "unresolved",
            "malformed_application",
        ):
            raise RuntimeError("Unsupported local replay scenario")
        return value

    if fault not in ("", "503"):
        raise RuntimeError("Unsupported local replay fault")
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    folder.chmod(0o700)
    config = Settings(
        database_url="sqlite:///" + str(folder / "sessions.sqlite3"),
        environment="test",
        requests_per_minute=1000,
        allowed_origins=("http://127.0.0.1:8081", "http://localhost:8081"),
        qloo_key="LOCAL_REPLAY_NO_REAL_KEY",
        qloo_calls_allowed=True,
        qloo_min_interval=0,
        qloo_cache_seconds=0 if fault_file else 3600,
        qloo_daily_requests=200,
    )
    searches = {}
    recommendations = {}
    for category in PAIRS:
        name, search, recs, seed = captured(category)
        searches[(name.casefold(), category)] = envelope(search)
        recommendations[seed["entity_id"].lower()] = envelope(recs)

    def replay(request):
        if request.url.host != "hackathon.api.qloo.com":
            raise RuntimeError("Replay host mismatch")
        active_fault = scenario()
        if request.url.path == "/search":
            if active_fault == "unresolved":
                return httpx.Response(404, json={"error": "Controlled unresolved seed"})
            key = (request.url.params["query"].casefold(), request.url.params["types"].replace("urn:entity:", ""))
            body = searches.get(key)
        elif request.url.path == "/v2/insights":
            if active_fault in ("400", "401", "403", "429", "503"):
                return httpx.Response(int(active_fault), json={"error": "Controlled private replay outage"})
            if active_fault == "network":
                raise httpx.ConnectError("Controlled replay connection failure", request=request)
            if active_fault == "timeout":
                raise httpx.ReadTimeout("Controlled replay timeout", request=request)
            if active_fault == "malformed":
                return httpx.Response(200, content=b"not JSON")
            if active_fault == "empty":
                return httpx.Response(200, json={"success": True, "results": {"entities": []}})
            body = recommendations.get(request.url.params["signal.interests.entities"].lower())
        else:
            raise RuntimeError("Unexpected replay operation")
        return httpx.Response(200, json=body) if body else httpx.Response(404, json={"error": "Unknown captured seed"})

    app = create_app(config, cultural_provider=CulturalProvider(config, httpx.MockTransport(replay)))
    app.state.verification_mode = "captured_response_replay"
    if fault_file:

        @app.middleware("http")
        async def controlled_application_response(request, call_next):
            if (
                request.method == "POST"
                and request.url.path == "/v1/sessions"
                and scenario() == "malformed_application"
            ):
                return Response(
                    b"not JSON",
                    media_type="application/json",
                    headers={"Access-Control-Allow-Origin": "http://127.0.0.1:8081"},
                )
            return await call_next(request)

    return app
