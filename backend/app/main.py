import logging
import re
import time
from collections import deque
from contextlib import asynccontextmanager
from threading import Lock
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .config import Settings
from .content import make_chapter
from .game_master import OpenAIResponsesGameMaster
from .local_game_master import OllamaGameMaster
from .models import (
    ActionRequest,
    CulturalEvidenceReply,
    DomainError,
    GameView,
    GenerationRecovery,
    NewGame,
    TurnRequest,
)
from .providers import CulturalProvider, UnavailableGameMaster
from .store import Store, owner_digest

logger = logging.getLogger("infinite_stories")


class Limiter:
    def __init__(self, limit):
        self.limit, self.buckets, self.lock = limit, {}, Lock()

    def accept(self, key):
        now = time.monotonic()
        with self.lock:
            if key not in self.buckets:
                if len(self.buckets) >= 4096:
                    self.buckets = {k: v for k, v in self.buckets.items() if v and v[-1] > now - 60}
                if len(self.buckets) >= 4096:
                    return False
                self.buckets[key] = deque()
            bucket = self.buckets[key]
            while bucket and bucket[0] <= now - 60:
                bucket.popleft()
            if len(bucket) >= self.limit:
                return False
            bucket.append(now)
            return True


def create_app(settings=None, game_master=None, cultural_provider=None):
    settings = (settings or Settings.from_env()).validate()
    chapter = make_chapter()

    @asynccontextmanager
    async def lifespan(app):
        app.state.store = Store(settings.database_url, chapter, settings.session_days, app.state.cultural_provider)
        app.state.cultural_provider.reserve_request = app.state.store.reserve_qloo_request
        try:
            yield
        finally:
            app.state.store.close()

    app = FastAPI(
        title="Infinite Stories",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
    )
    app.state.cultural_provider = cultural_provider or CulturalProvider(settings)
    app.state.chapter = chapter
    app.state.gm = game_master or (
        (OllamaGameMaster(settings) if settings.llm_provider == "ollama" else OpenAIResponsesGameMaster(settings))
        if settings.llm_calls_allowed
        else UnavailableGameMaster()
    )
    limiter = Limiter(settings.requests_per_minute)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["X-Request-ID"],
    )

    def error_response(request, code, message, status, details=None):
        return JSONResponse(
            {
                "error": {
                    "code": code,
                    "message": message,
                    "request_id": getattr(request.state, "correlation", ""),
                    **({"details": details} if details else {}),
                }
            },
            status_code=status,
        )

    @app.middleware("http")
    async def boundary(request, call_next):
        request.state.correlation = str(uuid4())
        start = time.monotonic()
        # IP limits apply in addition to per-token limits, so rotating guessed
        # bearer strings cannot bypass the anonymous session creation budget.
        ip_key = "ip:" + (request.client.host if request.client else "unknown")
        auth_key = "auth:" + owner_digest(request.headers.get("authorization", ""))
        if request.url.path not in ("/healthz", "/readyz") and (
            not limiter.accept(ip_key) or not limiter.accept(auth_key)
        ):
            response = error_response(request, "RATE_LIMITED", "Too many requests. Wait a minute before retrying.", 429)
            response.headers["Retry-After"] = "60"
        else:
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 16384:
                    break
                chunks.append(chunk)
            if size > 16384:
                response = error_response(request, "BODY_TOO_LARGE", "Request body exceeds 16 KiB.", 413)
            else:
                request._body = b"".join(chunks)
                response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.correlation
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        logger.info(
            "request id=%s status=%s elapsed_ms=%.1f",
            request.state.correlation,
            response.status_code,
            (time.monotonic() - start) * 1000,
        )
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request, error):
        return error_response(request, error.code, error.message, error.status, error.details)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, _):
        # Never echo request fields, prompts, credentials or body fragments.
        return error_response(request, "VALIDATION_ERROR", "Request fields are invalid or unsupported.", 422)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, _):
        return error_response(
            request,
            "STORAGE_UNAVAILABLE",
            "Progress could not be confirmed. Reload your last saved state before retrying.",
            503,
        )

    def token(authorization: str | None = Header(default=None)):
        if not authorization or not re.fullmatch(r"Bearer [A-Za-z0-9_-]{43,128}", authorization):
            raise DomainError("AUTH_REQUIRED", "A valid journey resume token is required.", 401)
        return authorization[7:]

    @app.get("/healthz")
    def health():
        return {"status": "ok", "service": "infinite-stories"}

    @app.get("/readyz")
    def ready(request: Request):
        with request.app.state.store.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return JSONResponse(
            {
                "status": "blocked",
                "storage": "ready",
                "authored_chapter": "ready",
                "qloo": app.state.cultural_provider.status,
                "game_master": "configured_not_live_verified" if app.state.gm.available else "unavailable",
            },
            status_code=503,
        )

    @app.get("/v1/capabilities")
    def capabilities():
        return {
            "schema_version": 1,
            "authored_chapter": True,
            "generic_control": True,
            "cultural_generation": app.state.cultural_provider.available,
            "cultural_categories": ["artist", "movie", "brand", "videogame"],
            "qloo_adapter_live_verified": False,
            "verification_mode": getattr(app.state, "verification_mode", ""),
            "game_master_configured": app.state.gm.available,
            "game_master_live_verified": False,
            "game_master_provider": getattr(getattr(app.state.gm, "settings", None), "llm_provider", ""),
            "game_master_inference_mode": (
                "local_loopback"
                if isinstance(app.state.gm, OllamaGameMaster)
                else "hosted"
                if isinstance(app.state.gm, OpenAIResponsesGameMaster)
                else "unavailable"
            ),
            "release_ready": False,
        }

    @app.get("/v1/chapter")
    def get_chapter():
        return chapter.model_dump()

    @app.post("/v1/sessions", response_model=GameView)
    def new_game(body: NewGame, request: Request, bearer=Depends(token)):
        return request.app.state.store.create(body, bearer)

    @app.post("/v1/sessions/recover", response_model=GameView)
    def recover_generation(body: GenerationRecovery, request: Request, bearer=Depends(token)):
        return request.app.state.store.recover_generation(body, bearer)

    @app.get("/v1/sessions/{session_id}", response_model=GameView)
    def get_game(session_id: UUID, request: Request, bearer=Depends(token)):
        return request.app.state.store.load(str(session_id), bearer)

    @app.post("/v1/sessions/{session_id}/actions", response_model=GameView)
    def action(session_id: UUID, body: ActionRequest, request: Request, bearer=Depends(token)):
        return request.app.state.store.action(str(session_id), bearer, body)

    @app.post("/v1/sessions/{session_id}/turns", response_model=GameView)
    async def turn(session_id: UUID, body: TurnRequest, request: Request, bearer=Depends(token)):
        store, gid = request.app.state.store, str(session_id)
        store.load(gid, bearer)  # Authenticate even when the provider is unavailable.
        if not app.state.gm.available:
            raise DomainError(
                "GAME_MASTER_UNAVAILABLE",
                "The Game Master is unavailable. Saved progress is safe; cultural explanations can be retried when it returns.",
                503,
            )
        previous, view = store.reserve_turn(gid, bearer, body, settings.llm_turn_limit, settings.llm_daily_turn_limit)
        if previous is not None:
            if "turn_error" in previous:
                raise DomainError(
                    previous["turn_error"],
                    "This turn failed without changing progress. It will not call the model again; retry with a new turn when the Game Master is available.",
                    503,
                )
            return {**previous, "idempotent_replay": True}
        try:
            result = await app.state.gm.run(chapter, view, body.text)
            proposal, narrative = result
            return store.finish_turn(
                gid,
                bearer,
                body,
                proposal,
                narrative,
                narrative_source=result.source
                if isinstance(result, CulturalEvidenceReply) and proposal is None
                else None,
                tool_results=result.observations if isinstance(result, CulturalEvidenceReply) else None,
                understanding=result.understanding if isinstance(result, CulturalEvidenceReply) else None,
            )
        except DomainError as error:
            store.fail_turn(gid, body.request_id, error.code)
            raise
        except Exception:
            store.fail_turn(gid, body.request_id, "MODEL_UPSTREAM_ERROR")
            raise DomainError(
                "MODEL_UPSTREAM_ERROR", "The Game Master is unavailable. Saved progress is unchanged.", 503
            ) from None

    @app.delete("/v1/sessions/{session_id}")
    def revoke(session_id: UUID, request: Request, bearer=Depends(token)):
        request.app.state.store.revoke(str(session_id), bearer)
        return {"status": "revoked"}

    return app
