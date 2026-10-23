"""Explicit historical Qloo replay + ACTUAL local Ollama, never hosted inference.

IS_CAPTURE_REPLAY_ONLY=1 IS_LOCAL_AI_VERIFICATION=1 \
IS_CAPTURE_REPLAY_DIRECTORY=reports/local/local-ai-game IS_LOCAL_MODEL_TAG=qwen3.5:4b \
.venv/bin/uvicorn scripts.local_ai_verification:create_local_ai_app --factory \
  --host 127.0.0.1 --port 8044

Use a client configured for this origin. Do not replace an existing replay server
or claim its browser evidence covers this server. Model installation is separate.
"""

import hashlib
import marshal
import os
from pathlib import Path

from backend.app import local_game_master
from backend.app.config import Settings
from backend.app.local_game_master import OllamaGameMaster
from backend.app.models import DomainError
from scripts.local_cultural_verification import create_verification_app


def create_local_ai_app():
    if os.getenv("IS_LOCAL_AI_VERIFICATION") != "1":
        raise RuntimeError("Explicit actual local inference opt-in required")
    # Require an isolated save directory; never reuse the browser acceptance DB.
    directory = os.getenv("IS_CAPTURE_REPLAY_DIRECTORY", "")
    if not directory or directory.endswith("client-cultural-verification"):
        raise RuntimeError("A separate local-AI verification save directory is required")
    config = Settings(
        llm_provider="ollama", llm_model=os.getenv("IS_LOCAL_MODEL_TAG", ""), llm_calls_allowed=True
    ).validate()
    app = create_verification_app()
    fault_file = os.getenv("IS_LOCAL_AI_FAULT_FILE", "")
    if fault_file:
        if Path(fault_file).resolve().parent != Path(directory).resolve():
            raise RuntimeError("Local model fault control must be inside the isolated save directory")

        class ControlledLocalGameMaster(OllamaGameMaster):
            async def run(self, *args):
                scenario = Path(fault_file).read_text().strip()
                if scenario == "unavailable":
                    raise DomainError(
                        "MODEL_UNAVAILABLE",
                        "Controlled local verification outage. Saved progress is unchanged; retry with a new turn after recovery.",
                        503,
                    )
                if scenario:
                    raise RuntimeError("Unknown local verification scenario")
                return await super().run(*args)

        app.state.gm = ControlledLocalGameMaster(config)
    else:
        app.state.gm = OllamaGameMaster(config)
    # Preserve the existing explicit Qloo replay label. The model is not replayed.
    app.state.local_ai_verification = True
    # Snapshot actual loaded code at startup; never infer loaded code from a
    # later disk read. This route exists only in the opted-in local factory.
    adapter = {
        "protocol": "ollama-understanding-v3",
        "pid": os.getpid(),
        "source_sha256_at_startup": hashlib.sha256(Path(local_game_master.__file__).read_bytes()).hexdigest(),
        # Marshal v3+ reference flags depend on live object refcounts. v2 avoids
        # a diagnostic changing merely because an async frame starts/stops.
        "loaded_method_sha256": {
            name: hashlib.sha256(marshal.dumps(getattr(OllamaGameMaster, name).__code__, 2)).hexdigest()
            for name in ("run", "_query", "_propose", "_assess_understanding")
        },
        "planner_fields": list(local_game_master.IntentPlan.model_fields),
        "model": config.llm_model,
        "verification_mode": "captured_response_replay",
        "inference_mode": "local_loopback",
    }

    @app.get("/verification/local-ai/adapter", include_in_schema=False)
    def loaded_adapter():
        return {**adapter, "latest_turn_inference_requests": app.state.gm.metrics.get("inference_requests")}

    return app
