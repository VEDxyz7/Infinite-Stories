from typing import Literal, NamedTuple
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


Category = Literal["artist", "movie", "brand", "videogame"]


class SavedInterest(StrictModel):
    # Existing authored saves can retain a deferred book interest without enabling it.
    name: str = Field(min_length=1, max_length=120)
    category: Literal["artist", "movie", "brand", "book", "videogame"]
    entity_id: UUID | None = None


class Interest(SavedInterest):
    category: Category

    @field_validator("entity_id", mode="before")
    @classmethod
    def empty_confirmation(cls, value):
        return None if value == "" else value

    @field_validator("name")
    @classmethod
    def clean_input(cls, value):
        value = value.strip()
        if not value or any(ord(c) < 32 for c in value):
            raise ValueError("Use a nonempty public cultural name")
        return value


class CulturalTag(StrictModel):
    id: str = Field(max_length=200)
    name: str = Field(max_length=120)
    type: str = Field(max_length=200)


class CulturalEntity(StrictModel):
    entity_id: UUID
    name: str = Field(min_length=1, max_length=200)
    category: Category
    description: str = Field(default="", max_length=1200)
    disambiguation: str = Field(default="", max_length=200)
    year: int | None = None
    content_rating: str = Field(default="", max_length=40)
    tags: list[CulturalTag] = Field(default_factory=list, max_length=40)


class CulturalRequest(StrictModel):
    origin: Literal["https://hackathon.api.qloo.com"] = "https://hackathon.api.qloo.com"
    path: Literal["/search", "/v2/insights"]
    params: dict[str, str]
    retrieved_at: str
    body_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    elapsed_ms: int = Field(ge=0)


class CulturalLink(StrictModel):
    seed: CulturalEntity
    recommendations: list[CulturalEntity] = Field(min_length=1, max_length=5)
    selected_id: UUID
    evidence: list[CulturalRequest] = Field(min_length=2, max_length=2)
    setting: str = Field(max_length=80)
    supporting_tag_id: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def verify_membership(self):
        target = "artist" if self.seed.category == "movie" else "movie"
        if any(e.category != target or e.entity_id == self.seed.entity_id for e in self.recommendations):
            raise ValueError("Invalid cross-category evidence")
        if len({e.entity_id for e in self.recommendations}) != len(self.recommendations):
            raise ValueError("Duplicate recommendations")
        selected = next((e for e in self.recommendations if e.entity_id == self.selected_id), None)
        if selected is None or (self.supporting_tag_id and self.supporting_tag_id not in {t.id for t in selected.tags}):
            raise ValueError("Unsupported selected result or tag")
        search, related = self.evidence
        if (
            search.path != "/search"
            or search.params.get("types") != "urn:entity:" + self.seed.category
            or related.path != "/v2/insights"
            or related.params.get("signal.interests.entities", "").lower() != str(self.seed.entity_id)
            or related.params.get("filter.type") != "urn:entity:" + target
        ):
            raise ValueError("Invalid request provenance")
        return self


class CulturalContext(StrictModel):
    schema_version: Literal[1] = 1
    source: Literal["qloo"] = "qloo"
    rule_version: Literal["cultural-cards-v1", "cultural-investigation-v2"] = "cultural-cards-v1"
    links: list[CulturalLink] = Field(min_length=1, max_length=5)


class NewGame(StrictModel):
    request_id: UUID
    mode: Literal["authored", "cultural"] = "cultural"
    interests: list[Interest] = Field(default_factory=list, max_length=5)


class GenerationRecovery(StrictModel):
    # Original creation payload binds recovery to its owner/idempotency hash.
    creation: NewGame
    previous_session_id: UUID | None = None

    @field_validator("previous_session_id", mode="before")
    @classmethod
    def empty_previous(cls, value):
        return None if value == "" else value

    @model_validator(mode="after")
    def cultural_only(self):
        if self.creation.mode != "cultural":
            raise ValueError("Generation recovery requires a cultural creation")
        return self


class Command(StrictModel):
    kind: Literal["position", "interact", "choose", "travel", "inspect"]
    target: str = Field(default="", max_length=80)
    choice: str = Field(default="", max_length=80)
    x: float = Field(default=0, ge=0, le=64)
    y: float = Field(default=0, ge=0, le=64)


class CulturalEvidenceReply(NamedTuple):
    """Model-selected read-only tool output, never model-generated factual prose."""

    proposal: Command | None
    narrative: str


class ActionRequest(StrictModel):
    request_id: UUID
    expected_revision: int = Field(ge=0)
    command: Command


class TurnRequest(StrictModel):
    request_id: UUID
    expected_revision: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=1000)


class GameState(StrictModel):
    schema_version: Literal[1] = 1
    chapter_id: Literal["last_light"] = "last_light"
    chapter_version: Literal[1] = 1
    mode: Literal["authored", "cultural"] = "authored"
    location_id: str = "quay"
    x: float = 4
    y: float = 5
    visits: int = Field(default=1, ge=1, le=12)
    flags: list[str] = Field(default_factory=list)
    choices: list[str] = Field(default_factory=list)
    interests: list[SavedInterest] = Field(default_factory=list)
    ending: str = ""
    history: list[str] = Field(
        default_factory=lambda: ["The last tram leaves at dawn. Find three memories before the city closes its gates."]
    )
    cultural_source: Literal["none", "qloo"] = "none"
    cultural_context: CulturalContext | None = None

    @model_validator(mode="after")
    def consistent_source(self):
        if (self.mode == "cultural") != (self.cultural_context is not None) or (self.cultural_source == "qloo") != (
            self.mode == "cultural"
        ):
            raise ValueError("Inconsistent cultural state attribution")
        return self


class Choice(StrictModel):
    id: str
    label: str
    requires: list[str] = Field(default_factory=list)
    grants: list[str] = Field(default_factory=list)
    text: str
    ending: str = ""


class WorldObject(StrictModel):
    id: str
    name: str
    kind: Literal["npc", "object", "portal", "gate"]
    x: float
    y: float
    text: str
    destination: str = ""
    choices: list[Choice] = Field(default_factory=list)


class Location(StrictModel):
    id: str
    name: str
    description: str
    width: int = Field(ge=8, le=64)
    height: int = Field(ge=8, le=64)
    rows: list[str]
    objects: list[WorldObject]


class Chapter(StrictModel):
    schema_version: Literal[1]
    id: Literal["last_light"]
    version: Literal[1]
    title: str
    source: Literal["authored_original", "qloo_informed"]
    locations: list[Location]


class Objective(StrictModel):
    id: str
    label: str
    completed: bool


class GameView(StrictModel):
    schema_version: Literal[1] = 1
    session_id: str = Field(min_length=1, max_length=80)
    revision: int = Field(ge=0)
    state: GameState
    location: Location
    nearby: list[WorldObject]
    objectives: list[Objective]
    narrative: str = Field(default="", max_length=2000)
    narrative_source: Literal[
        "authored", "game_master_validated", "game_master_no_state_change", "cultural_evidence_tool"
    ] = "authored"
    idempotent_replay: bool = False
    notices: list[str]


class DomainError(Exception):
    def __init__(self, code: str, message: str, status: int = 409, details: dict | None = None):
        self.code, self.message, self.status, self.details = code, message, status, details
        super().__init__(code)
