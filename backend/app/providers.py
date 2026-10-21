"""Server-only Qloo adapter over the documented Search and Insights GET workflow.

Zero automatic retries. Calls require explicit configuration. HTTP transports can
be injected for deterministic tests; production never reads replay files.
"""

import hashlib
import json
import threading
import time
import unicodedata
from collections import OrderedDict
from datetime import datetime, timezone
from uuid import UUID

import httpx
from pydantic import ValidationError

from .config import Settings
from .culture import SETTINGS, select_setting
from .models import CulturalContext, CulturalEntity, CulturalLink, CulturalRequest, CulturalTag, DomainError

DIRECTIONS = {"artist": "movie", "movie": "artist", "brand": "movie", "videogame": "movie"}
HOST = "https://hackathon.api.qloo.com"


def normalized(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def entity_from_data(data, expected):
    if not isinstance(data, dict):
        raise ValueError("Entity must be an object")
    actual = data.get("subtype") or (expected if "urn:entity:" + expected in data.get("types", []) else None)
    if actual not in (expected, "urn:entity:" + expected):
        raise ValueError("Wrong category")
    props = data.get("properties", {})
    if not isinstance(props, dict):
        raise ValueError("Invalid metadata")
    tags = []
    source_tags = data.get("tags", [])
    if not isinstance(source_tags, list):
        raise ValueError("Invalid tags")
    source_tags = sorted(
        (t for t in source_tags if isinstance(t, dict)), key=lambda t: (t.get("id") or t.get("tag_id")) not in SETTINGS
    )
    for tag in source_tags[:12]:
        if not isinstance(tag, dict):
            continue
        tag_id = tag.get("id") or tag.get("tag_id")
        if all(isinstance(x, str) and x for x in (tag_id, tag.get("name"), tag.get("type"))):
            tags.append(CulturalTag(id=tag_id[:200], name=tag["name"][:120], type=tag["type"][:200]))
    description = props.get("description") or props.get("short_description") or ""
    if not isinstance(description, str):
        description = ""
    return CulturalEntity(
        entity_id=UUID(data["entity_id"]),
        name=data["name"],
        category=expected,
        disambiguation=data.get("disambiguation") or "",
        description=description[:400],
        year=props.get("release_year"),
        content_rating=props.get("content_rating") or "",
        tags=tags,
    )


class CulturalProvider:
    def __init__(self, settings=None, transport=None, reserve_request=None):
        self.settings = (settings or Settings()).validate()
        self.transport = transport
        self.reserve_request = reserve_request
        self._lock = threading.Lock()
        self._cache = OrderedDict()
        self._last = 0.0

    @property
    def available(self):
        return self.settings.qloo_calls_allowed and bool(self.settings.qloo_key)

    @property
    def status(self):
        return "configured_not_live_verified" if self.available else "disabled"

    def _get(self, client, path, params, deadline):
        cache_key = (path, tuple(sorted(params.items())))
        now = time.monotonic()
        if cache_key in self._cache:
            expires, body, proof = self._cache[cache_key]
            if expires > now:
                self._cache.move_to_end(cache_key)
                return body, proof
            del self._cache[cache_key]
        delay = max(0, self.settings.qloo_min_interval - (now - self._last))
        if deadline - now <= delay:
            raise DomainError("QLOO_TIMEOUT", "Cultural generation reached its time limit. No world was changed.", 503)
        if delay:
            time.sleep(delay)
        if self.reserve_request:
            self.reserve_request(self.settings.qloo_daily_requests)
        self._last = time.monotonic()
        start = time.monotonic()
        try:
            with client.stream(
                "GET",
                HOST + path,
                params=params,
                headers={"X-Api-Key": self.settings.qloo_key, "Accept": "application/json"},
                timeout=max(0.1, min(15, deadline - start)),
            ) as response:
                status = response.status_code
                if status in (401, 403):
                    raise DomainError(
                        "QLOO_AUTH", "The cultural service credential or category is not authorized.", 503
                    )
                if status == 429:
                    raise DomainError(
                        "QLOO_RATE_LIMIT", "The cultural service is rate limited. No world was changed.", 429
                    )
                if status == 404 and path == "/search":
                    raise DomainError(
                        "QLOO_UNRESOLVED", "No cultural entity matched. Check the name and category.", 422
                    )
                if status == 400:
                    raise DomainError(
                        "QLOO_REQUEST_REJECTED",
                        "The cultural service rejected this seed or query. Choose another interest; no world was changed.",
                        422,
                    )
                if status != 200:
                    raise DomainError(
                        "QLOO_UPSTREAM",
                        "The cultural service rejected the request or is unavailable. No world was changed.",
                        503,
                    )
                raw = bytearray()
                for chunk in response.iter_bytes():
                    if time.monotonic() > deadline:
                        raise DomainError(
                            "QLOO_TIMEOUT", "Cultural generation reached its time limit. No world was changed.", 503
                        )
                    raw.extend(chunk)
                    if len(raw) > 2_000_000:
                        raise ValueError("Response too large")
                body = json.loads(raw)
                if not isinstance(body, dict) or body.get("success") is False:
                    raise ValueError("Invalid response envelope")
                results = body.get("results")
                entries = (
                    results if path == "/search" else results.get("entities") if isinstance(results, dict) else None
                )
                if not isinstance(entries, list):
                    raise ValueError("Unknown response schema")
                if len(entries) > 5:
                    raise ValueError("Unbounded entity collection")
                if not entries:
                    raise DomainError(
                        "QLOO_EMPTY", "No cultural results are available for that seed. Choose another interest.", 422
                    )
                proof = CulturalRequest(
                    path=path,
                    params=params,
                    retrieved_at=datetime.now(timezone.utc).isoformat(),
                    body_sha256=hashlib.sha256(raw).hexdigest(),
                    elapsed_ms=round((time.monotonic() - start) * 1000),
                )
                if self.settings.qloo_cache_seconds:
                    self._cache[cache_key] = (time.monotonic() + self.settings.qloo_cache_seconds, body, proof)
                    while len(self._cache) > 128:
                        self._cache.popitem(last=False)
                return body, proof
        except DomainError:
            raise
        except httpx.TimeoutException:
            raise DomainError("QLOO_TIMEOUT", "The cultural service timed out. No world was changed.", 503) from None
        except httpx.HTTPError:
            raise DomainError(
                "QLOO_NETWORK", "The cultural service could not be reached. No world was changed.", 503
            ) from None
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise DomainError(
                "QLOO_RESPONSE_INVALID", "The cultural service returned unsupported data. No world was changed.", 503
            ) from None

    def generate(self, interests):
        if not self.available:
            raise DomainError(
                "QLOO_NOT_VERIFIED", "Cultural generation is disabled pending authorized server configuration.", 503
            )
        if not 1 <= len(interests) <= 5 or any(i.category not in DIRECTIONS for i in interests):
            raise DomainError(
                "QLOO_INPUT_INVALID", "Select one to five supported artist, film, brand or game interests.", 422
            )
        deadline = time.monotonic() + 45
        if not self._lock.acquire(timeout=45):
            raise DomainError("QLOO_BUSY", "Cultural generation is busy. No world was changed.", 503)
        try:
            links = []
            with httpx.Client(transport=self.transport, trust_env=False, follow_redirects=False) as client:
                for index, interest in enumerate(interests):
                    body, search_proof = self._get(
                        client,
                        "/search",
                        {"query": interest.name, "types": "urn:entity:" + interest.category, "take": "5"},
                        deadline,
                    )
                    candidates = []
                    for entry in body["results"]:
                        try:
                            candidate = entity_from_data(entry, interest.category)
                            if candidate.entity_id not in {c.entity_id for c in candidates}:
                                candidates.append(candidate)
                        except (ValueError, TypeError, KeyError, AttributeError, ValidationError):
                            continue
                    if not candidates:
                        raise DomainError("QLOO_RESPONSE_INVALID", "No identifiable entities were returned.", 503)
                    matches = (
                        [e for e in candidates if e.entity_id == interest.entity_id]
                        if interest.entity_id
                        else [e for e in candidates if normalized(e.name) == normalized(interest.name)]
                    )
                    if len(matches) != 1:
                        raise DomainError(
                            "QLOO_AMBIGUOUS",
                            "Confirm which cultural entity you mean before generating a world.",
                            409,
                            {
                                "interest_index": index,
                                "candidates": [
                                    {
                                        "entity_id": str(e.entity_id),
                                        "name": e.name,
                                        "category": e.category,
                                        "disambiguation": e.disambiguation,
                                    }
                                    for e in candidates
                                ],
                            },
                        )
                    seed = matches[0]
                    target = DIRECTIONS[interest.category]
                    body, rec_proof = self._get(
                        client,
                        "/v2/insights",
                        {
                            "filter.type": "urn:entity:" + target,
                            "signal.interests.entities": str(seed.entity_id).upper(),
                            "take": "5",
                        },
                        deadline,
                    )
                    entities = []
                    for entry in body["results"]["entities"]:
                        try:
                            entity = entity_from_data(entry, target)
                            if entity.entity_id != seed.entity_id and entity.entity_id not in {
                                e.entity_id for e in entities
                            }:
                                entities.append(entity)
                        except (ValueError, TypeError, KeyError, AttributeError, ValidationError):
                            continue
                    if not entities:
                        raise DomainError(
                            "QLOO_UNUSABLE", "No valid cross-category recommendations were returned.", 422
                        )
                    selected, setting, tag = select_setting(seed, entities)
                    links.append(
                        CulturalLink(
                            seed=seed,
                            recommendations=entities[:5],
                            selected_id=selected,
                            evidence=[search_proof, rec_proof],
                            setting=setting,
                            supporting_tag_id=tag,
                        )
                    )
            return CulturalContext(links=links)
        finally:
            self._lock.release()


class UnavailableGameMaster:
    available = False

    async def run(self, *args):
        raise DomainError(
            "GAME_MASTER_UNAVAILABLE",
            "Free-form actions are unavailable. Your progress is safe and the predefined choices still work.",
            503,
        )
