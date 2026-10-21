"""Isolated visual-review backend. Captured Qloo replay only; never reads .env.

IS_CAPTURE_REPLAY_ONLY=1 IS_CAPTURE_REPLAY_DIRECTORY=<private new directory>
.venv/bin/python -m uvicorn scripts.visual_verification:create_app --factory --host 127.0.0.1 --port 8045
Serve client/Builds/VisualVerification on loopback8082. No production changes.
"""
from scripts.local_cultural_verification import create_verification_app


def create_app():
    app = create_verification_app()
    for middleware in app.user_middleware:
        if middleware.cls.__name__ == "CORSMiddleware":
            middleware.kwargs["allow_origins"] = ["http://127.0.0.1:8082", "http://localhost:8082"]
    return app
