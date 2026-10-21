"""The visual-review service is opt-in replay, not a live-provider fallback."""
import pytest
from fastapi.testclient import TestClient

from scripts.visual_verification import create_app


def test_visual_review_requires_explicit_capture_opt_in(monkeypatch):
    monkeypatch.delenv("IS_CAPTURE_REPLAY_ONLY", raising=False)
    with pytest.raises(RuntimeError, match="Explicit captured-response"):
        create_app()


def test_visual_review_is_isolated_replay_with_loopback_cors(monkeypatch, tmp_path):
    monkeypatch.setenv("IS_CAPTURE_REPLAY_ONLY", "1")
    monkeypatch.setenv("IS_CAPTURE_REPLAY_DIRECTORY", str(tmp_path))
    monkeypatch.delenv("IS_CAPTURE_REPLAY_FAULT_FILE", raising=False)
    with TestClient(create_app()) as client:
        response = client.get("/v1/capabilities", headers={"Origin": "http://127.0.0.1:8082"})
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:8082"
        body = response.json()
        assert body["verification_mode"] == "captured_response_replay"
        assert set(body["cultural_categories"]) == {"artist", "movie", "brand", "videogame"}
        response = client.get("/v1/capabilities", headers={"Origin": "https://unrelated.invalid"})
        assert "access-control-allow-origin" not in response.headers
