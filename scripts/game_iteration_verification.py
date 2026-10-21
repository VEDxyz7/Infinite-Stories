"""Opted-in local agent + captured Qloo, isolated investigation verification only."""

from scripts.local_ai_verification import create_local_ai_app


def create_app():
    app = create_local_ai_app()
    for middleware in app.user_middleware:
        if middleware.cls.__name__ == "CORSMiddleware":
            middleware.kwargs["allow_origins"] = ["http://127.0.0.1:8085", "http://localhost:8085"]
    return app
