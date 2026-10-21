#!/usr/bin/env python3
"""Disposable Phase 0 probe. Stdlib only; offline by default; never claims a game PASS.

REST workflow: docs/API_INTEGRATION.md. Event kit prefers its public
harness; this REST adapter requires organizer approval before live use.
"""
import argparse
import collections
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://api.qloo.com"
TAKE = 5
MAX_CALLS = 24  # Includes errors; automatic retries = 0.
MAX_BODY = 2_000_000
CASES = [
    ("Björk", "artist", "movie"),
    ("A. R. Rahman", "artist", "movie"),
    ("Spirited Away", "movie", "brand"),
    ("Inception", "movie", "brand"),
    ("Nike", "brand", "artist"),
    ("Patagonia", "brand", "artist"),
    ("Dune", "book", "movie"),
    ("Hades", "videogame", "brand"),
]
CONTRACT = "https://github.com/qloo/docs-public/tree/d4a0eb978518f7fb404993d1509d11b21239ada6"


def timestamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def is_uuid(value):
    try:
        uuid.UUID(value)
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def load_env(path):
    """Literal KEY=value only: no shell, interpolation, execution, or value logging."""
    if not path.exists():
        return {}
    result = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError("Invalid environment file syntax")
        key, value = line.split("=", 1)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key.strip()):
            raise ValueError("Invalid environment variable name")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        result[key.strip()] = value
    return result


def redact(value, secrets):
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, list):
        return [redact(v, secrets) for v in value]
    if isinstance(value, dict):
        return {redact(k, secrets): redact(v, secrets) for k, v in value.items()
                if not re.search(r"api.?key|authorization|cookie|token|password|secret", k, re.I)}
    return value


def extract_entities(body, search=False):
    """Search containers are provisional decoders, NOT a verified search schema.

    Insights results.entities is in the official example. Unknown shapes fail
    closed and are recorded as SCHEMA_UNKNOWN, never as an empty successful test.
    """
    if not isinstance(body, dict) or body.get("success") is False:
        return None
    result = body.get("results")
    if isinstance(result, dict) and isinstance(result.get("entities"), list):
        return result["entities"]
    if search and isinstance(result, list):
        return result
    return None


def entity_view(entity):
    if not isinstance(entity, dict):
        return {}
    out = {k: entity[k] for k in ("entity_id", "name", "type", "subtype", "popularity", "disambiguation") if k in entity}
    props = entity.get("properties", {})
    if isinstance(props, dict):
        out["properties"] = {k: props[k] for k in ("release_year", "publication_year") if k in props}
    if isinstance(entity.get("tags"), list):
        out["tags"] = [{k: tag[k] for k in ("id", "name", "type") if k in tag}
                       for tag in entity["tags"][:50] if isinstance(tag, dict)]
    # Preserve explanatory evidence only when actually present. Shape is unverified.
    query = entity.get("query")
    if isinstance(query, dict):
        out["query"] = {"explainability": query["explainability"]} if "explainability" in query else {}
        out["query_fields_present"] = sorted(query)  # Discover schema without inventing a score path.
    return out


def resolve(candidates, name, category):
    expected = "urn:entity:" + category
    matches = [c for c in candidates if isinstance(c, dict)
               and normalize(str(c.get("name", ""))) == normalize(name)
               and (c.get("subtype") or c.get("type")) == expected
               and is_uuid(c.get("entity_id"))]
    if len(matches) == 1:
        return "EXACT_CANDIDATE_REQUIRES_CONFIRMATION", matches[0]
    return ("AMBIGUOUS" if len(matches) > 1 else "UNRESOLVED"), None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward credentials to a redirect destination.


class Probe:
    def __init__(self, key, base_url=BASE):
        self.key = key
        self.base_url = base_url
        self.records = []
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def get(self, path, params):
        if path not in ("/search", "/v2/insights") or len(self.records) >= MAX_CALLS:
            raise ValueError("Read-only endpoint or request budget violation")
        if self.records:
            time.sleep(1)  # Conservative pacing, NOT a verified account rate limit.
        record = {"request_id": f"q{len(self.records)+1:02}", "at_utc": timestamp(),
                  "source": "live_qloo", "method": "GET", "base_url": self.base_url,
                  "path": path, "params": params, "contract": CONTRACT}
        self.records.append(record)
        request = urllib.request.Request(self.base_url + path + "?" + urllib.parse.urlencode(params),
                    headers={"X-Api-Key": self.key, "Accept": "application/json"}, method="GET")
        try:
            with self.opener.open(request, timeout=15) as response:
                record["http_status"] = response.status
                raw = response.read(MAX_BODY + 1)
                if len(raw) > MAX_BODY:
                    record["outcome"] = "BODY_LIMIT"
                    return None
                record["body_sha256"] = hashlib.sha256(raw).hexdigest()
                body = json.loads(raw)
                entities = extract_entities(body, search=path == "/search")
                if entities is None:
                    record["outcome"] = "SCHEMA_UNKNOWN"
                    return None
                record["result_count"] = len(entities)
                record["categories"] = dict(collections.Counter(
                    str(c.get("subtype") or c.get("type") or "MISSING")
                    for c in entities if isinstance(c, dict)))
                record["entities"] = [entity_view(c) for c in entities]
                record["outcome"] = "DATA_RETURNED_UNVALIDATED" if entities else "EMPTY"
                top_query = body.get("query")
                if isinstance(top_query, dict) and "explainability" in top_query:
                    record["explainability"] = top_query["explainability"]
                return entities
        except urllib.error.HTTPError as exc:
            record.update(http_status=exc.code, outcome="HTTP_ERROR")
            exc.close()  # Never log response error bodies or arbitrary headers.
        except (TimeoutError, socket.timeout):
            record["outcome"] = "TIMEOUT"
        except urllib.error.URLError:
            record["outcome"] = "NETWORK_OR_TLS_ERROR"
        except (ValueError, UnicodeError):
            record["outcome"] = "INVALID_JSON"
        return None

    def recommend(self, ids, target):
        return self.get("/v2/insights", {"filter.type": "urn:entity:" + target,
            "signal.interests.entities": ",".join(ids), "filter.exclude.entities": ",".join(ids),
            "feature.explainability": "true", "take": TAKE, "page": 1})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Requires credentials and verified usage permissions")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args = parser.parse_args(argv)
    plan = {"mode": "live" if args.live else "offline_plan", "at_utc": timestamp(),
            "status": "NOT TESTED", "max_calls": MAX_CALLS, "automatic_retries": 0,
            "cases": [{"name": n, "category": c, "target": t} for n, c, t in CASES]}
    if not args.live:
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return 0
    env = {**load_env(args.env_file), **os.environ}
    key = env.get("QLOO_API_KEY", "")
    blockers = []
    if not key or "REPLACE_WITH" in key or key.lower() in ("placeholder", "your-api-key"):
        blockers.append("Missing usable QLOO_API_KEY")
    base_url = env.get("QLOO_APPROVED_BASE_URL", "").rstrip("/")
    # The credential grant must establish its host. Neither old production
    # examples nor a speculative hackathon hostname authorize key transmission.
    if (env.get("QLOO_ENDPOINT_CONFIRMED", "").lower() != "true" or
            base_url not in ("https://api.qloo.com", "https://hackathon.api.qloo.com")):
        blockers.append("Organizer-verified event API origin is not confirmed")
    for flag, reason in [
        ("QLOO_NONBILLABLE_CONFIRMED", "Nonbillable quota/rate/expiry not confirmed"),
        ("QLOO_DIRECT_REST_APPROVED", "Organizer approval for direct REST adapter not confirmed"),
        ("QLOO_LOCAL_RETENTION_CONFIRMED", "Local sanitized evidence retention permission not confirmed")]:
        if env.get(flag, "").lower() != "true":
            blockers.append(reason)
    if blockers:
        print(json.dumps({"status": "BLOCKED", "at_utc": timestamp(), "api_requests": 0, "blockers": blockers}))
        return 2
    probe = Probe(key, base_url)
    resolved = {}
    rows = []
    stop = False
    for name, category, target in CASES:
        candidates = probe.get("/search", {"query": name, "types": "urn:entity:" + category,
                                              "take": TAKE, "page": 1, "sort_by": "match"})
        row = {"input": name, "category": category, "target": target,
               "search_request_id": probe.records[-1]["request_id"]}
        rows.append(row)
        if candidates is None:
            row["resolution"] = "SEARCH_ERROR_OR_SCHEMA_UNKNOWN"
        else:
            state, match = resolve(candidates, name, category)
            row["resolution"] = state
            if match:
                # This measures provisional coverage; player-confirmed resolution is untested.
                resolved[name] = match["entity_id"]
                row["candidate"] = entity_view(match)
                related = probe.recommend([match["entity_id"]], target)
                row["related_request_id"] = probe.records[-1]["request_id"]
                row["usable_target_count"] = sum(1 for e in related or [] if isinstance(e, dict)
                    and is_uuid(e.get("entity_id")) and bool(e.get("name"))
                    and (e.get("subtype") or e.get("type")) == "urn:entity:" + target)
                if category == "artist" and related:
                    movie = next((e for e in related if isinstance(e, dict) and is_uuid(e.get("entity_id"))
                                  and e.get("subtype") == "urn:entity:movie"), None)
                    if movie:
                        probe.recommend([movie["entity_id"]], "brand")
                        row["second_hop_request_id"] = probe.records[-1]["request_id"]
        if any(r.get("http_status") in (401, 403, 429) for r in probe.records):
            stop = True
            break
    # Two deliberately different seed sets, only if each seed resolves.
    profiles = []
    if not stop:
        for names in (("Björk", "Spirited Away", "Patagonia"), ("A. R. Rahman", "Inception", "Nike")):
            if all(name in resolved for name in names):
                for target in ("movie", "brand"):
                    data = probe.recommend([resolved[n] for n in names], target)
                    profiles.append({"inputs": list(names), "target": target,
                        "request_id": probe.records[-1]["request_id"],
                        "entity_ids": sorted(e["entity_id"] for e in data or []
                                             if isinstance(e, dict) and is_uuid(e.get("entity_id")))})
                    if probe.records[-1].get("http_status") in (401, 403, 429):
                        stop = True
                        break
            if stop:
                break
    report = {"source": "live_qloo_sanitized_projection", "at_utc": timestamp(),
              "status": "PARTIAL_REQUIRES_EVIDENCE_REVIEW", "api_requests": len(probe.records),
              "rows": rows, "profiles": profiles, "requests": probe.records,
              "limitations": ["Search response decoder and explainability shape need live verification",
                  "Exact name match is only a candidate; human confirmation still required",
                  "No game capability or solvability PASS is assigned automatically",
                  "Sanitized projection omits raw data; raw-body hash cannot replay the whole body"]}
    secrets = [v for k, v in env.items() if re.search(r"KEY|TOKEN|SECRET|PASSWORD", k, re.I)]
    report = redact(report, secrets)
    folder = ROOT / "tests/fixtures/local"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    filename = folder / ("qloo-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8] + ".json")
    fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as out:
        json.dump(report, out, indent=2, ensure_ascii=False)
    print(json.dumps({"status": report["status"], "api_requests": len(probe.records),
                      "fixture": str(filename.relative_to(ROOT))}))
    return 1 if stop or any(r["outcome"] != "DATA_RETURNED_UNVALIDATED" for r in probe.records) else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError):
        print(json.dumps({"status": "ERROR", "reason": "Local configuration, budget, or output error; details suppressed"}))
        raise SystemExit(1)
