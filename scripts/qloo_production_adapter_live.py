"""One-shot authorized production-adapter acceptance. Default mode is network-free.

Uses normal Settings.from_env/create_app/Store/CulturalProvider. The real outbound
HTTPTransport has retries=0 and a two-request host/path/verified-UUID guard.
Never stores headers, keys or raw provider bodies. The exclusive ledger prevents
accidental reuse of this consumed authorization.
"""

import argparse
import hashlib
import json
import logging
import os
import secrets
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import CulturalContext
from backend.app.providers import CulturalProvider, entity_from_data, normalized
from backend.tests.test_service import action, choose, move, visit_next

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "reports/local/qloo-production-adapter-20261020"
OUTPUT = ROOT / "reports/QLOO_PRODUCTION_ADAPTER_LIVE_20261020.json"
HOST = "hackathon.api.qloo.com"


def stamp():
    return datetime.now(timezone.utc).isoformat()


def credential():
    key = os.getenv("QLOO_API_KEY", "")
    if not key:
        for line in (ROOT / ".env").read_text().splitlines():
            name, separator, value = line.strip().partition("=")
            if separator and name.strip() == "QLOO_API_KEY":
                key = value.strip()
                if len(key) > 1 and key[0] == key[-1] and key[0] in "\"'":
                    key = key[1:-1]
                break
    if not key or key.startswith(("REPLACE_", "YOUR_")):
        raise RuntimeError("Private Qloo credential unavailable; no live request sent")
    return key


class TwoRequestRealTransport(httpx.BaseTransport):
    def __init__(self, save):
        self.delegate = httpx.HTTPTransport(retries=0)
        self.records = []
        self.verified_id = None
        self.save = save

    def handle_request(self, request):
        number = len(self.records) + 1
        expected = (
            {"query": "Björk", "types": "urn:entity:artist", "take": "5"}
            if number == 1
            else {
                "filter.type": "urn:entity:movie",
                "signal.interests.entities": (self.verified_id or "").upper(),
                "take": "5",
            }
        )
        if (
            number > 2
            or request.method != "GET"
            or request.url.scheme != "https"
            or request.url.host != HOST
            or request.url.port not in (None, 443)
            or request.url.path != ("/search" if number == 1 else "/v2/insights")
            or dict(request.url.params) != expected
            or (number == 2 and self.verified_id is None)
        ):
            raise RuntimeError("Two-request live authorization guard rejected operation before network")
        record = {
            "request_number": number,
            "operation": "artist_resolution" if number == 1 else "artist_to_film_recommendations",
            "path": request.url.path,
            "at_utc": stamp(),
            "http_status": None,
            "elapsed_ms": None,
            "production_adapter_invoked": True,
            "transport": "real_httpx_HTTPTransport_retries0",
        }
        self.records.append(record)
        self.save()
        start = time.monotonic()
        try:
            response = self.delegate.handle_request(request)
            record["http_status"] = response.status_code
            # Read original response for complete-body timing, return the SAME
            # real response object/content to production decoding/normalization.
            raw = response.read()
            record["elapsed_ms"] = round((time.monotonic() - start) * 1000)
            record["response_sha256"] = hashlib.sha256(raw).hexdigest()
            if len(raw) <= 2_000_000 and response.status_code == 200:
                try:
                    body = json.loads(raw)
                    entities = body.get("results") if number == 1 else body.get("results", {}).get("entities")
                    if isinstance(entities, list):
                        record["returned_count"] = len(entities)
                        valid = []
                        for item in entities:
                            try:
                                valid.append(entity_from_data(item, "artist" if number == 1 else "movie"))
                            except (ValueError, TypeError, KeyError, AttributeError):
                                continue
                        record["normalized_valid_count"] = len(valid)
                        if number == 1:
                            matches = [e for e in valid if normalized(e.name) == normalized("Björk")]
                            record["unique_exact_artist_match"] = len(matches) == 1
                            if len(matches) == 1:
                                self.verified_id = str(matches[0].entity_id)
                                record["resolved_entity"] = matches[0].model_dump(mode="json")
                        else:
                            record["normalized_entities"] = [e.model_dump(mode="json") for e in valid]
                except (ValueError, TypeError, AttributeError):
                    record["sanitized_payload_error"] = "Unrecognized or invalid JSON/entity structure"
            return response
        except httpx.HTTPError as error:
            record["elapsed_ms"] = round((time.monotonic() - start) * 1000)
            record["sanitized_transport_error"] = type(error).__name__
            raise
        finally:
            self.save()

    def close(self):
        self.delegate.close()


def public_projection(report):
    """Publish only bounded identity/useful-field examples, never full payloads."""
    public = json.loads(json.dumps(report))

    def entity_summary(entity):
        summary = {
            k: entity.get(k) for k in ("entity_id", "name", "category", "disambiguation", "year", "content_rating")
        }
        summary["description_excerpt"] = entity.get("description", "")[:160]
        tags = entity.get("tags", [])
        summary["normalized_tag_count"] = len(tags)
        summary["tag_examples"] = [
            tag
            for tag in tags
            if tag["id"] == "urn:tag:theme:qloo:art_and_creativity" or tag["type"] == "urn:tag:genre"
        ][:3]
        return summary

    for operation in public.get("operations", []):
        if "resolved_entity" in operation:
            operation["resolved_entity"] = entity_summary(operation["resolved_entity"])
        if "normalized_entities" in operation:
            operation["normalized_entities"] = [entity_summary(e) for e in operation["normalized_entities"]]
    if "context" in public:
        public["context"]["seed"] = entity_summary(public["context"]["seed"])
    public["normalized_evidence_scope"] = (
        "Minimal useful-field examples; full validated context remains only in the private session DB. No raw bodies or headers saved."
    )
    return public


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-authorized-two", action="store_true")
    args = parser.parse_args()
    if not args.execute_authorized_two:
        print(
            "Offline plan only: production cultural-session creation, Björk artist Search then verified-ID film Insights; maximum2, retries0. No calls made."
        )
        return
    if OUTPUT.exists():
        raise SystemExit("Live evidence already exists; authorization cannot be reused")
    key = credential()
    PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    PRIVATE.chmod(0o700)
    ledger = PRIVATE / "authorization-reservation.json"
    # No network before this exclusive reservation. Never delete it to rerun.
    with ledger.open("x") as stream:
        stream.write('{"reserved":true,"requests":[]}\n')
    ledger.chmod(0o600)
    os.environ.update(
        {
            "QLOO_API_KEY": key,
            "QLOO_BASE_URL": "https://hackathon.api.qloo.com",
            "IS_QLOO_CALLS_ALLOWED": "true",
            "IS_QLOO_DAILY_REQUESTS": "2",
            "IS_QLOO_CACHE_SECONDS": "0",
            "IS_DATABASE_URL": "sqlite:///" + str(PRIVATE / "sessions.sqlite3"),
            "IS_ENVIRONMENT": "development",
            "IS_REQUESTS_PER_MINUTE": "1000",
            "IS_LLM_CALLS_ALLOWED": "false",
            "IS_LLM_PROVIDER": "",
            "IS_LLM_MODEL": "",
            "IS_LLM_API_KEY": "",
            "OPENAI_API_KEY": "",
        }
    )
    config = Settings.from_env()
    report = {
        "kind": "authorized_live_production_adapter_two_request_acceptance",
        "at_utc": stamp(),
        "historical_requests_before": 12,
        "new_live_qloo_requests": 0,
        "new_openai_requests": 0,
        "base_url": config.qloo_base_url,
        "retries": 0,
        "redirects": False,
        "replay_used": False,
        "settings_path": "Settings.from_env",
        "backend_path": "create_app → Store.create → CulturalProvider.generate",
        "database": "private isolated SQLite; normal development backend configuration",
        "operations": [],
        "adapter_live_verdict": "FAIL",
        "downstream": {"status": "NOT_RUN"},
        "overall_release": "BLOCKED",
    }
    guard = None

    def save():
        if guard:
            report["operations"] = guard.records
            report["new_live_qloo_requests"] = len(guard.records)
        ledger.write_text(json.dumps({"reserved": True, "requests": report["operations"]}, indent=2) + "\n")
        OUTPUT.write_text(json.dumps(public_projection(report), indent=2) + "\n")

    guard = TwoRequestRealTransport(save)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    app = create_app(config)
    assert type(app.state.cultural_provider) is CulturalProvider
    assert app.state.cultural_provider.transport is None
    app.state.cultural_provider.transport = guard  # Real guarded transport, NEVER MockTransport.
    headers = {"Authorization": "Bearer " + secrets.token_urlsafe(32)}
    body = {"request_id": str(uuid4()), "mode": "cultural", "interests": [{"name": "Björk", "category": "artist"}]}
    try:
        with TestClient(app) as client:
            response = client.post("/v1/sessions", headers=headers, json=body)
            report["session_creation_http_status"] = response.status_code
            if response.status_code != 200:
                error = response.json().get("error", {})
                report["sanitized_error"] = {k: error[k] for k in ("code", "message") if k in error}
                return
            view = response.json()
            assert len(guard.records) == 2 and all(r["http_status"] == 200 for r in guard.records)
            context = CulturalContext.model_validate(view["state"]["cultural_context"])
            link = context.links[0]
            assert str(link.seed.entity_id) == guard.verified_id and link.seed.category == "artist"
            for operation, evidence in zip(guard.records, link.evidence, strict=True):
                assert operation["response_sha256"] == evidence.body_sha256
                operation["adapter_elapsed_ms"] = evidence.elapsed_ms
                operation["normalization_and_provenance"] = "PASS"
            report["adapter_live_verdict"] = "PASS"
            report["context"] = {
                "seed": link.seed.model_dump(mode="json"),
                "recommendation_count": len(link.recommendations),
                "selected_id": str(link.selected_id),
                "setting": link.setting,
                "supporting_tag_id": link.supporting_tag_id,
                "request_provenance": [e.model_dump(mode="json") for e in link.evidence],
            }
            report["downstream"] = {
                "status": "IN_PROGRESS",
                "checks": ["actual live context attached to intended cultural session"],
            }
            # Live authority consumed. All following operations are local only.
            app.state.cultural_provider = CulturalProvider(replace(config, qloo_calls_allowed=False, qloo_key=""))
            app.state.store.cultural_provider = app.state.cultural_provider
            assert client.post("/v1/sessions", headers=headers, json=body).json()["session_id"] == view["session_id"]
            report["downstream"]["checks"].append("completed creation replays without provider availability")
            view = choose(client, headers, view, "mara", "take_map")
            view = choose(client, headers, visit_next(client, headers, view), "ivo", "learn_rhythm")
            view = move(client, headers, visit_next(client, headers, view), 14, 9)
            assert (
                action(
                    client, headers, view, {"kind": "choose", "target": "sera", "choice": "promise_guard"}
                ).status_code
                == 409
            )
            card = next(o for o in view["location"]["objects"] if o["id"] == "cultural_echo_0")
            assert str(link.selected_id) in card["choices"][0]["id"]
            view = move(client, headers, view, card["x"], card["y"])
            assert (
                action(
                    client, headers, view, {"kind": "choose", "target": card["id"], "choice": "fabricated"}
                ).status_code
                == 409
            )
            taken = action(
                client, headers, view, {"kind": "choose", "target": card["id"], "choice": card["choices"][0]["id"]}
            )
            assert taken.status_code == 200
            view = choose(client, headers, taken.json(), "sera", "promise_guard")
            view = choose(client, headers, visit_next(client, headers, view), "beacon", "light_together")
            assert view["state"]["ending"] == "together" and view["state"]["visits"] == 4
            report["downstream"]["checks"].extend(
                [
                    "required card contains actual selected recommendation UUID",
                    "Sera blocked until cultural card",
                    "fabricated answer rejected409",
                    "actual card changes quest flags and enables four-visit ending",
                ]
            )
        with TestClient(create_app(replace(config, qloo_calls_allowed=False, qloo_key=""))) as restarted:
            loaded = restarted.get("/v1/sessions/" + view["session_id"], headers=headers)
            assert loaded.status_code == 200
            assert loaded.json()["state"] == view["state"] and loaded.json()["revision"] == view["revision"]
            assert loaded.json()["state"]["cultural_context"] == context.model_dump(mode="json")
            assert restarted.post("/v1/sessions", headers=headers, json=body).json()["state"] == view["state"]
        assert len(guard.records) == 2
        report["downstream"].update(
            status="PASS", ending=view["state"]["ending"], visits=view["state"]["visits"], revision=view["revision"]
        )
        report["downstream"]["checks"].append(
            "app/store restart, exact state/context/progress resume and creation receipt replay with provider disabled"
        )
    except Exception as error:
        report["local_validation_error_type"] = type(error).__name__
        if report["downstream"]["status"] == "IN_PROGRESS":
            report["downstream"]["status"] = "FAIL"
    finally:
        save()
        print(
            json.dumps(
                {
                    "live_requests_sent": report["new_live_qloo_requests"],
                    "adapter_live_verdict": report["adapter_live_verdict"],
                    "downstream_status": report["downstream"]["status"],
                    "evidence": str(OUTPUT.relative_to(ROOT)),
                }
            )
        )


if __name__ == "__main__":
    main()
