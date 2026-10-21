#!/usr/bin/env python3
"""Real local HTTP smoke; never calls an external provider or prints resume credentials."""

import json
import secrets
from uuid import uuid4

import httpx


def main():
    evidence = {"transport": "real_loopback_http", "provider_calls": 0, "checks": []}
    with httpx.Client(base_url="http://127.0.0.1:8042", timeout=10, trust_env=False) as client:

        def record(name, actual, expected):
            assert actual == expected, (name, actual, expected)
            evidence["checks"].append({"check": name, "actual": actual, "expected": expected})

        record("liveness", client.get("/healthz").status_code, 200)
        record("release_readiness_blocked", client.get("/readyz").status_code, 503)
        headers = {"Authorization": "Bearer " + secrets.token_urlsafe(32)}
        response = client.post(
            "/v1/sessions", headers=headers, json={"request_id": str(uuid4()), "mode": "authored", "interests": []}
        )
        record("new_authored_journey", response.status_code, 200)
        view = response.json()
        base = "/v1/sessions/" + view["session_id"]
        record("resume", client.get(base, headers=headers).status_code, 200)
        request = {"request_id": str(uuid4()), "expected_revision": 0, "command": {"kind": "position", "x": 5, "y": 5}}
        response = client.post(base + "/actions", headers=headers, json=request)
        record("move_confirmed", response.status_code, 200)
        record("move_revision", response.json()["revision"], 1)
        record(
            "duplicate_action_not_reapplied",
            client.post(base + "/actions", headers=headers, json=request).json()["revision"],
            1,
        )
        response = client.post(
            "/v1/sessions", headers=headers, json={"request_id": str(uuid4()), "mode": "cultural", "interests": []}
        )
        record("cultural_generation_unavailable", response.status_code, 503)
        record("cultural_error", response.json()["error"]["code"], "QLOO_NOT_VERIFIED")
        record("revoke", client.delete(base, headers=headers).status_code, 200)
        record("revoked_save_inaccessible", client.get(base, headers=headers).status_code, 404)
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
