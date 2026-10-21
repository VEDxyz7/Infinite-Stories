"""Transactional snapshots and idempotent action receipts; SQLite locally/Postgres in deployment."""

import hashlib
import json
import secrets
import time
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import (
    JSON,
    Column,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    event,
    insert,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError

from .content import current_location
from .culture import chapter_for_state
from .engine import apply_command, game_view
from .models import DomainError, GameState

metadata = MetaData()
migrations = Table("schema_migrations", metadata, Column("version", Integer, primary_key=True))
games = Table(
    "games",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("owner", String(64), nullable=False),
    Column("create_id", String(36), nullable=False),
    Column("create_hash", String(64), nullable=False),
    Column("state", JSON, nullable=False),
    Column("state_hash", String(64), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("expires", Float, nullable=False),
    Column("gm_turns", Integer, nullable=False, default=0),
    UniqueConstraint("owner", "create_id"),
)
receipts = Table(
    "action_receipts",
    metadata,
    Column("game_id", String(36), primary_key=True),
    Column("request_id", String(36), primary_key=True),
    Column("payload_hash", String(64), nullable=False),
    Column("response", JSON, nullable=False),
)
turns = Table(
    "gm_turns",
    metadata,
    Column("game_id", String(36), primary_key=True),
    Column("request_id", String(36), primary_key=True),
    Column("payload_hash", String(64), nullable=False),
    Column("status", String(16), nullable=False),
    Column("response", JSON),
    Column("created", Float, nullable=False),
)
daily_budget = Table(
    "model_daily_budget", metadata, Column("day", Integer, primary_key=True), Column("used", Integer, nullable=False)
)

generations = Table(
    "cultural_generations",
    metadata,
    Column("owner", String(64), primary_key=True),
    Column("request_id", String(36), primary_key=True),
    Column("payload_hash", String(64), nullable=False),
    Column("status", String(16), nullable=False),
    Column("error", JSON),
    Column("created", Float, nullable=False),
)
qloo_budget = Table(
    "qloo_daily_budget", metadata, Column("day", Integer, primary_key=True), Column("used", Integer, nullable=False)
)


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def owner_digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


class Store:
    def __init__(self, url, chapter, session_days=30, cultural_provider=None):
        self.chapter, self.session_days, self.cultural_provider = chapter, session_days, cultural_provider
        if url.startswith("sqlite:///") and not url.endswith(":memory:"):
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        kwargs = {"connect_args": {"check_same_thread": False, "timeout": 10}} if url.startswith("sqlite") else {}
        self.engine = create_engine(url, pool_pre_ping=True, **kwargs)
        if url.startswith("sqlite"):

            @event.listens_for(self.engine, "connect")
            def configure_sqlite(connection, _):
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("PRAGMA foreign_keys=ON")

        with self.engine.begin() as connection:
            migrations.create(connection, checkfirst=True)
            versions = connection.execute(select(migrations.c.version)).scalars().all()
            if versions and versions not in ([1], [2], [3]):
                raise ValueError("Database schema is unsupported; migration required")
            metadata.create_all(connection)
            if not versions:
                connection.execute(insert(migrations).values(version=3))
            elif versions in ([1], [2]):
                connection.execute(update(migrations).values(version=3))
        if url.startswith("sqlite:///") and not url.endswith(":memory:"):
            Path(url.removeprefix("sqlite:///")).chmod(0o600)

    def close(self):
        self.engine.dispose()

    def _row(self, connection, game_id, token):
        row = (
            connection.execute(select(games).where(games.c.id == game_id, games.c.owner == owner_digest(token)))
            .mappings()
            .first()
        )
        if not row or row["expires"] <= time.time():
            raise DomainError("SESSION_UNAVAILABLE", "This save is unavailable or your session has expired.", 404)
        if not secrets.compare_digest(row["state_hash"], digest(row["state"])):
            raise DomainError("SAVE_INVALID", "This save failed its integrity check. It has not been overwritten.", 503)
        try:
            state = GameState.model_validate(row["state"])
        except ValidationError:
            raise DomainError("SAVE_INVALID", "This save version cannot be safely resumed.", 503) from None
        current_location(chapter_for_state(self.chapter, state), state)
        return row, state

    def reserve_qloo_request(self, limit):
        day = int(time.time() // 86400)
        dialect_insert = sqlite_insert if self.engine.dialect.name == "sqlite" else postgres_insert
        with self.engine.begin() as connection:
            connection.execute(dialect_insert(qloo_budget).values(day=day, used=0).on_conflict_do_nothing())
            result = connection.execute(
                update(qloo_budget)
                .where(qloo_budget.c.day == day, qloo_budget.c.used < limit)
                .values(used=qloo_budget.c.used + 1)
            )
            if result.rowcount != 1:
                raise DomainError(
                    "QLOO_APP_BUDGET",
                    "The service's cultural request budget is exhausted. Existing journeys remain playable.",
                    429,
                )

    def create(self, request, token):
        owner = owner_digest(token)
        fingerprint = digest(request.model_dump(mode="json", exclude_none=True))
        rid = str(request.request_id)
        # Replays load persisted context without a new provider request, even if
        # calls are disabled after restart. The ownership check still applies.
        with self.engine.connect() as connection:
            existing = (
                connection.execute(select(games).where(games.c.owner == owner, games.c.create_id == rid))
                .mappings()
                .first()
            )
            if existing:
                if existing["create_hash"] != fingerprint:
                    raise DomainError(
                        "IDEMPOTENCY_CONFLICT", "This request ID was already used with different content."
                    )
                row, state = self._row(connection, existing["id"], token)
                return game_view(self.chapter, state, row["id"], row["revision"])
        context = None
        if request.mode == "cultural":
            if not self.cultural_provider or not self.cultural_provider.available:
                raise DomainError(
                    "QLOO_NOT_VERIFIED", "Cultural generation is disabled pending authorized server configuration.", 503
                )
            if not request.interests:
                raise DomainError("QLOO_INPUT_INVALID", "Add at least one supported cultural interest.", 422)
            try:
                with self.engine.begin() as connection:
                    prior = (
                        connection.execute(
                            select(generations).where(generations.c.owner == owner, generations.c.request_id == rid)
                        )
                        .mappings()
                        .first()
                    )
                    if prior:
                        if prior["payload_hash"] != fingerprint:
                            raise DomainError(
                                "IDEMPOTENCY_CONFLICT", "This request ID was already used with different content."
                            )
                        if prior["status"] == "failed":
                            error = prior["error"]
                            raise DomainError(error["code"], error["message"], error["status"], error.get("details"))
                        raise DomainError(
                            "QLOO_GENERATION_PENDING",
                            "This generation is pending or was interrupted. No duplicate provider calls will be made.",
                        )
                    connection.execute(
                        insert(generations).values(
                            owner=owner, request_id=rid, payload_hash=fingerprint, status="pending", created=time.time()
                        )
                    )
            except IntegrityError:
                raise DomainError(
                    "QLOO_GENERATION_PENDING",
                    "This generation is already reserved. No duplicate provider calls will be made.",
                ) from None
            try:
                context = self.cultural_provider.generate(request.interests)
                # Validate all generated content before opening the save transaction.
                state = GameState(
                    mode="cultural", interests=request.interests, cultural_source="qloo", cultural_context=context
                )
                chapter_for_state(self.chapter, state)
            except Exception as error:
                safe = (
                    error
                    if isinstance(error, DomainError)
                    else DomainError(
                        "QLOO_RESPONSE_INVALID", "Cultural generation failed validation. No world was changed.", 503
                    )
                )
                with self.engine.begin() as connection:
                    connection.execute(
                        update(generations)
                        .where(generations.c.owner == owner, generations.c.request_id == rid)
                        .values(
                            status="failed",
                            error={
                                "code": safe.code,
                                "message": safe.message,
                                "status": safe.status,
                                "details": safe.details,
                            },
                        )
                    )
                raise safe from None
        else:
            state = GameState(interests=request.interests)
        data = state.model_dump(mode="json")
        gid = str(uuid4())
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    insert(games).values(
                        id=gid,
                        owner=owner,
                        create_id=rid,
                        create_hash=fingerprint,
                        state=data,
                        state_hash=digest(data),
                        revision=0,
                        expires=time.time() + 86400 * self.session_days,
                        gm_turns=0,
                    )
                )
                if context is not None:
                    connection.execute(
                        update(generations)
                        .where(generations.c.owner == owner, generations.c.request_id == rid)
                        .values(status="complete")
                    )
                return game_view(self.chapter, state, gid, 0, state.history[-1])
        except IntegrityError:
            # Authored concurrent creation shares the existing receipt as well.
            with self.engine.connect() as connection:
                existing = (
                    connection.execute(select(games).where(games.c.owner == owner, games.c.create_id == rid))
                    .mappings()
                    .first()
                )
                if not existing or existing["create_hash"] != fingerprint:
                    raise DomainError(
                        "IDEMPOTENCY_CONFLICT", "Concurrent creation differs from this request."
                    ) from None
                row, state = self._row(connection, existing["id"], token)
                return game_view(self.chapter, state, row["id"], row["revision"])

    def load(self, gid, token):
        with self.engine.connect() as connection:
            row, state = self._row(connection, gid, token)
            return game_view(self.chapter, state, gid, row["revision"])

    def _apply(self, connection, gid, token, request):
        row, state = self._row(connection, gid, token)
        fingerprint = digest(request.model_dump(mode="json"))
        previous = (
            connection.execute(
                select(receipts).where(receipts.c.game_id == gid, receipts.c.request_id == str(request.request_id))
            )
            .mappings()
            .first()
        )
        if previous:
            if previous["payload_hash"] != fingerprint:
                raise DomainError("IDEMPOTENCY_CONFLICT", "This request ID was already used with different content.")
            # Keep receipts compact: ordinary position saves must not duplicate
            # the whole chapter/map in SQL. Replays return latest confirmed
            # progress, never an old snapshot that could roll a client back.
            view = game_view(
                self.chapter,
                state,
                gid,
                row["revision"],
                "That action was already confirmed. Your latest save is loaded.",
            )
            return {**view, "idempotent_replay": True}
        if row["revision"] != request.expected_revision:
            raise DomainError(
                "STALE_REVISION", "Progress changed in another request. Reload the confirmed save before trying again."
            )
        changed, narrative = apply_command(self.chapter, state, request.command)
        data = changed.model_dump(mode="json")
        revision = row["revision"] + 1
        result = connection.execute(
            update(games)
            .where(games.c.id == gid, games.c.revision == row["revision"])
            .values(state=data, state_hash=digest(data), revision=revision)
        )
        if result.rowcount != 1:
            raise DomainError("STALE_REVISION", "Progress changed; reload your save.")
        response = game_view(self.chapter, changed, gid, revision, narrative)
        connection.execute(
            insert(receipts).values(
                game_id=gid,
                request_id=str(request.request_id),
                payload_hash=fingerprint,
                response={"result_revision": revision},
            )
        )
        return response

    def action(self, gid, token, request):
        try:
            with self.engine.begin() as connection:
                return self._apply(connection, gid, token, request)
        except IntegrityError:
            # A concurrent duplicate is never applied a second time.
            with self.engine.begin() as connection:
                return self._apply(connection, gid, token, request)

    def reserve_turn(self, gid, token, request, limit, daily_limit=20):
        fingerprint = digest(request.model_dump(mode="json"))
        try:
            with self.engine.begin() as connection:
                row, state = self._row(connection, gid, token)
                existing = (
                    connection.execute(
                        select(turns).where(turns.c.game_id == gid, turns.c.request_id == str(request.request_id))
                    )
                    .mappings()
                    .first()
                )
                if existing:
                    if existing["payload_hash"] != fingerprint:
                        raise DomainError("IDEMPOTENCY_CONFLICT", "This turn ID was used with different content.")
                    if existing["status"] == "pending":
                        raise DomainError(
                            "TURN_PENDING",
                            "This turn is pending or was interrupted. Reload confirmed progress; it will not be charged again.",
                        )
                    return existing["response"], None
                if row["revision"] != request.expected_revision:
                    raise DomainError("STALE_REVISION", "Reload the latest confirmed progress first.")
                if state.ending:
                    raise DomainError("STORY_COMPLETE", "This chapter has concluded.")
                day = int(time.time() // 86400)  # UTC budget boundary, shared across sessions/processes.
                dialect_insert = sqlite_insert if self.engine.dialect.name == "sqlite" else postgres_insert
                connection.execute(dialect_insert(daily_budget).values(day=day, used=0).on_conflict_do_nothing())
                budget = connection.execute(
                    update(daily_budget)
                    .where(daily_budget.c.day == day, daily_budget.c.used < daily_limit)
                    .values(used=daily_budget.c.used + 1)
                )
                if budget.rowcount != 1:
                    raise DomainError(
                        "MODEL_DAILY_BUDGET",
                        "The service's daily free-form action budget is exhausted. Predefined choices remain available.",
                        429,
                    )
                changed = connection.execute(
                    update(games)
                    .where(games.c.id == gid, games.c.gm_turns < limit)
                    .values(gm_turns=games.c.gm_turns + 1)
                )
                if changed.rowcount != 1:
                    raise DomainError(
                        "MODEL_BUDGET_EXHAUSTED",
                        "This journey has reached its free-form turn budget. The predefined choices remain available.",
                        429,
                    )
                connection.execute(
                    insert(turns).values(
                        game_id=gid,
                        request_id=str(request.request_id),
                        payload_hash=fingerprint,
                        status="pending",
                        created=time.time(),
                    )
                )
                view = game_view(self.chapter, state, gid, row["revision"])
                # Bounded saved narration, not prompts or credentials. Survives restart.
                recent = (
                    connection.execute(
                        select(turns.c.response)
                        .where(turns.c.game_id == gid, turns.c.status == "complete")
                        .order_by(turns.c.created.desc())
                        .limit(5)
                    )
                    .scalars()
                    .all()
                )
                view["recent_dialogue"] = [
                    r["narrative"] for r in reversed(recent) if r and isinstance(r.get("narrative"), str)
                ]
                return None, view
        except IntegrityError:
            raise DomainError(
                "TURN_PENDING", "A duplicate turn is already pending; no second model call was started."
            ) from None

    def finish_turn(self, gid, token, turn_request, proposal, narrative, narrative_source=None):
        from .models import ActionRequest

        if narrative_source is not None and (narrative_source != "cultural_evidence_tool" or proposal is not None):
            raise DomainError("MODEL_OUTPUT_INVALID", "A read-only evidence reply cannot change progress.", 503)

        with self.engine.begin() as connection:
            if proposal is not None:
                action = ActionRequest(
                    request_id=turn_request.request_id,
                    expected_revision=turn_request.expected_revision,
                    command=proposal,
                )
                response = self._apply(connection, gid, token, action)
                # State-changing narration is always the authoritative engine's text.
            else:
                row, state = self._row(connection, gid, token)
                if row["revision"] != turn_request.expected_revision:
                    raise DomainError(
                        "STALE_REVISION",
                        "Progress changed while the Game Master was thinking. Your progress is intact.",
                    )
                response = game_view(self.chapter, state, gid, row["revision"], narrative)
            response["narrative_source"] = narrative_source or (
                "game_master_validated" if proposal is not None else "game_master_no_state_change"
            )
            connection.execute(
                update(turns)
                .where(turns.c.game_id == gid, turns.c.request_id == str(turn_request.request_id))
                .values(status="complete", response=response)
            )
            return response

    def fail_turn(self, gid, request_id, code):
        # No prompt or provider raw error is retained. Failed IDs are terminal.
        with self.engine.begin() as connection:
            connection.execute(
                update(turns)
                .where(turns.c.game_id == gid, turns.c.request_id == str(request_id))
                .values(status="failed", response={"turn_error": code})
            )

    def revoke(self, gid, token):
        with self.engine.begin() as connection:
            self._row(connection, gid, token)
            connection.execute(update(games).where(games.c.id == gid).values(expires=time.time()))
