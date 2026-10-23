from dataclasses import dataclass, field
from typing import Literal
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
    rule_version: Literal["cultural-cards-v1", "cultural-investigation-v2", "cultural-understanding-v3"] = (
        "cultural-cards-v1"
    )
    links: list[CulturalLink] = Field(min_length=1, max_length=5)


class NewGame(StrictModel):
    request_id: UUID
    mode: Literal["authored", "cultural", "generic_control"] = "cultural"
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


class UnderstandingAssessment(StrictModel):
    attempt: bool
    choice_id: str = Field(max_length=80)
    status: Literal["supported", "incomplete", "unsupported", "unclear"]
    link_index: int = Field(ge=0, le=4)
    source_id: UUID | None
    target_id: UUID | None
    # Verbatim spans bind the semantic classification to the actual player turn.
    connection_quote: str = Field(max_length=1000)
    limitation_quote: str = Field(max_length=1000)
    interpretation_quote: str = Field(max_length=1000)
    commitment_quote: str = Field(default="", max_length=1000)
    addresses_affinity: bool
    respects_limits: bool
    separates_fiction: bool
    explicit_choice: bool


class PromiseUnderstanding(StrictModel):
    choice_quote: str = Field(max_length=1000)
    fiction_quote: str = Field(max_length=1000)
    fiction_meaning: Literal["distinguishes_fiction", "not_explained", "claims_fact"]
    choice_meaning: Literal["sharing", "guarding", "no_commitment"]


class UnderstandingReview(StrictModel):
    connection_meaning: Literal[
        "association_explanation", "names_only", "different_or_invented_pair", "unsupported_claim", "unclear"
    ]
    limitation_meaning: Literal["acknowledges_evidence_limits", "request_or_promise", "absent_or_contradicted"]
    fiction_meaning: Literal["distinguishes_fiction", "not_explained", "claims_fact"]
    choice_meaning: Literal["present_sharing", "present_guarding", "past_or_absent"]


class UnderstandingRecord(StrictModel):
    resident: Literal["mara", "ivo", "sera", "beacon"]
    choice_id: str = Field(min_length=1, max_length=80)
    evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    assessment: UnderstandingAssessment
    review: UnderstandingReview
    explanation: str = Field(min_length=1, max_length=1000)


class Command(StrictModel):
    kind: Literal["position", "interact", "choose", "travel", "inspect"]
    target: str = Field(default="", max_length=80)
    choice: str = Field(default="", max_length=80)
    x: float = Field(default=0, ge=0, le=64)
    y: float = Field(default=0, ge=0, le=64)


class ToolObservation(StrictModel):
    tool_id: Literal[
        "search_entities", "get_related_entities", "inspect_connection", "check_progress", "record_discovery"
    ]
    arguments: dict
    result: dict


@dataclass
class CulturalEvidenceReply:
    """Backend tool observation, never model-generated factual prose.

    Two-value iteration preserves the existing internal proposal/narrative API.
    """

    proposal: Command | None
    narrative: str
    observations: list[ToolObservation] = field(default_factory=list)
    source: str | None = "cultural_evidence_tool"
    understanding: dict | None = None

    def __iter__(self):
        yield self.proposal
        yield self.narrative


class ActionRequest(StrictModel):
    request_id: UUID
    expected_revision: int = Field(ge=0)
    command: Command


class TurnRequest(StrictModel):
    request_id: UUID
    expected_revision: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=1000)


class CulturalDistance(StrictModel):
    source_id: UUID
    target_id: UUID
    contrast: float | None = Field(default=None, ge=0, le=1)
    metadata_status: Literal["comparable", "unknown"]
    comparable_domains: list[str] = Field(default_factory=list)
    shared_tags: list[str] = Field(default_factory=list)
    relationship: Literal["direct_saved_recommendation", "not_evaluated"] = "not_evaluated"
    paths: list[list[UUID]] = Field(default_factory=list, max_length=6)
    method: Literal["application-tag-jaccard-v1"] = "application-tag-jaccard-v1"

    @model_validator(mode="after")
    def consistent_distance(self):
        if (self.contrast is None) != (self.metadata_status == "unknown"):
            raise ValueError("Unknown contrast cannot be represented as a number")
        if self.metadata_status == "unknown" and (self.comparable_domains or self.shared_tags):
            raise ValueError("Unknown contrast has no comparable tag sets")
        if self.metadata_status == "comparable" and not self.comparable_domains:
            raise ValueError("Contrast requires comparable tag domains")
        if any(
            len(path) not in (2, 3) or path[0] != self.source_id or path[-1] != self.target_id for path in self.paths
        ):
            raise ValueError("Invalid saved evidence path")
        return self


class CityGeneration(StrictModel):
    version: Literal["saved-cultural-city-v1"] = "saved-cultural-city-v1"
    seed: str = Field(pattern=r"^[a-f0-9]{64}$")
    candidate: int = Field(ge=0, le=2)
    template: int = Field(ge=0, le=2)
    proof_order: list[int] = Field(min_length=1, max_length=5)
    trace_locations: list[Literal["quay", "market", "archive"]] = Field(min_length=1, max_length=5)
    card_locations: list[Literal["quay", "market", "archive"]] = Field(min_length=1, max_length=5)
    resident_links: dict[str, int]
    distances: list[CulturalDistance] = Field(min_length=1, max_length=5)
    shortcut: list[Literal["quay", "market", "archive", "station"]] = Field(default_factory=list, max_length=2)


class ActivationValidation(StrictModel):
    version: Literal["engine-witness-v1"]
    candidate: int = Field(ge=0, le=2)
    evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    chapter_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    generation_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    generated_chapter_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    commands_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    steps: int = Field(ge=1, le=100000)
    visits: int = Field(ge=1, le=12)
    ending: Literal["together", "keeper"]


class GenericControl(StrictModel):
    version: Literal["synthetic-control-v1"] = "synthetic-control-v1"
    seed: Literal["last-light-control-v1"] = "last-light-control-v1"
    source: Literal["invented_demo"] = "invented_demo"
    # Not CulturalEntity: no fabricated Qloo UUID, request provenance or affinity.
    record: Literal["The Lantern Waltz"] = "The Lantern Waltz"
    film: Literal["Paper Moon Tram"] = "Paper Moon Tram"
    motif: Literal["three amber circles"] = "three amber circles"


class TasteRelationship(StrictModel):
    source: CulturalEntity
    target: CulturalEntity
    provenance: list[CulturalRequest]
    explanation: str


class TasteCard(StrictModel):
    version: Literal["taste-card-v1"] = "taste-card-v1"
    domain: Literal["qloo", "authored", "invented_demo"]
    ending: Literal["together", "keeper", "dawn"]
    favourites: list[SavedInterest]
    discoveries: list[str]
    encountered: list[CulturalEntity]
    relationships: list[TasteRelationship]
    profile: str
    profile_basis: str
    metadata_labels: list[str]
    try_next: list[TasteRelationship]
    recommendations_note: str


class GameState(StrictModel):
    schema_version: Literal[1] = 1
    chapter_id: Literal["last_light"] = "last_light"
    chapter_version: Literal[1] = 1
    mode: Literal["authored", "cultural", "generic_control"] = "authored"
    location_id: str = "quay"
    x: float = 4
    y: float = 5
    # Missing fields identify legacy saves; never reinterpret their clock.
    visit_rules: Literal["travel-v1", "conversation-v1"] = "travel-v1"
    visits: int = Field(default=1, ge=0, le=12)
    encounter_id: str = ""
    activation_validation: ActivationValidation | None = None
    city_generation: CityGeneration | None = None
    flags: list[str] = Field(default_factory=list)
    choices: list[str] = Field(default_factory=list)
    understanding_records: list[UnderstandingRecord] = Field(default_factory=list, max_length=32)
    interests: list[SavedInterest] = Field(default_factory=list)
    ending: str = ""
    history: list[str] = Field(
        default_factory=lambda: ["The last tram leaves at dawn. Find three memories before the city closes its gates."]
    )
    cultural_source: Literal["none", "qloo"] = "none"
    cultural_context: CulturalContext | None = None
    generic_control: GenericControl | None = None
    taste_card: TasteCard | None = None

    @model_validator(mode="after")
    def consistent_source(self):
        if (self.mode == "generic_control") != (self.generic_control is not None):
            raise ValueError("Synthetic control requires its isolated versioned scenario")
        if self.taste_card is not None:
            domain = "qloo" if self.mode == "cultural" else "invented_demo" if self.generic_control else "authored"
            if self.taste_card.ending != self.ending or self.taste_card.domain != domain:
                raise ValueError("Taste Card must match a completed run and evidence domain")
        if self.visit_rules == "travel-v1" and self.visits < 1:
            raise ValueError("Legacy travel saves start at visit one")
        if (self.mode == "cultural") != (self.cultural_context is not None) or (self.cultural_source == "qloo") != (
            self.mode == "cultural"
        ):
            raise ValueError("Inconsistent cultural state attribution")
        if self.city_generation is not None:
            plan = self.city_generation
            if (
                self.visit_rules != "conversation-v1"
                or self.cultural_context is None
                or self.cultural_context.rule_version != "cultural-understanding-v3"
            ):
                raise ValueError("Procedural plan requires its versioned cultural context")
            count = len(self.cultural_context.links)
            if sorted(plan.proof_order) != list(range(count)) or any(
                len(values) != count for values in (plan.trace_locations, plan.card_locations, plan.distances)
            ):
                raise ValueError("Incomplete city plan")
            if set(plan.resident_links) != {"mara", "ivo", "sera"} or any(
                i not in range(count) for i in plan.resident_links.values()
            ):
                raise ValueError("Invalid resident evidence assignment")
            favourites = {link.seed.entity_id for link in self.cultural_context.links}
            if any(link.selected_id in favourites for link in self.cultural_context.links):
                raise ValueError("A procedural centre cannot be an explicitly selected favourite")
            for i, measure in enumerate(plan.distances):
                link = self.cultural_context.links[i]
                if (
                    measure.source_id != link.seed.entity_id
                    or measure.target_id != link.selected_id
                    or measure.relationship != "direct_saved_recommendation"
                ):
                    raise ValueError("City measure is not bound to selected saved evidence")
                if [measure.source_id, measure.target_id] not in measure.paths:
                    raise ValueError("City proof has no direct saved path")
            if plan.shortcut and (len(plan.shortcut) != 2 or plan.shortcut[0] == plan.shortcut[1]):
                raise ValueError("Invalid city passage")
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
        "authored",
        "game_master_validated",
        "game_master_no_state_change",
        "cultural_evidence_tool",
        "confirmed_state_tool",
    ] = "authored"
    tool_results: list[ToolObservation] = Field(default_factory=list, max_length=2)
    idempotent_replay: bool = False
    notices: list[str]


class DomainError(Exception):
    def __init__(self, code: str, message: str, status: int = 409, details: dict | None = None):
        self.code, self.message, self.status, self.details = code, message, status, details
        super().__init__(code)
