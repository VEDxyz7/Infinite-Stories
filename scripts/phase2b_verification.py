"""Explicit local Ollama + historical Qloo replay for the Phase2B browser build.

Uses a new private save directory and loopback8083/8084 and8046 only. Never reads .env.
"""

from scripts.local_ai_verification import create_local_ai_app


def create_app():
    app = create_local_ai_app()
    for middleware in app.user_middleware:
        if middleware.cls.__name__ == "CORSMiddleware":
            middleware.kwargs["allow_origins"] = [
                "http://127.0.0.1:8083",
                "http://localhost:8083",
                "http://127.0.0.1:8084",
                "http://localhost:8084",
            ]
    return app
