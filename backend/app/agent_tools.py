"""Five scoped tools over an authenticated, reserved server snapshot.

No provider/network access. Mutations are proposals only: Store.finish_turn
commits them using the owning turn ID, revision CAS and durable action receipt.
"""

from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from .culture import cultural_evidence_text
from .engine import apply_command, game_view
from .models import Command, CulturalEntity, CulturalRequest, DomainError, GameState, Objective, StrictModel


class SearchArguments(StrictModel):
    query: str = Field(min_length=1, max_length=120)
    category: Literal["any", "artist", "movie", "brand", "videogame"] = "any"

    @field_validator("query")
    @classmethod
    def nonblank(cls, value):
        value = value.strip()
        if not value or any(ord(c) < 32 for c in value):
            raise ValueError("Use a public nonempty catalogue query")
        return value


class RelatedArguments(StrictModel):
    entity_id: UUID | None


class ConnectionArguments(StrictModel):
    pair: Literal["selected", "specified"] = "selected"
    source_id: UUID | None = None
    target_id: UUID | None = None
    claim: Literal["affinity", "collaboration", "personality"] = "affinity"


class ProgressArguments(StrictModel):
    scope: Literal["all", "inventory", "commitments", "visits", "objectives"] = "all"


class DiscoveryArguments(StrictModel):
    requested_name: str = Field(max_length=200)
    action_id: str = Field(min_length=1, max_length=200)


class SearchResult(StrictModel):
    status: Literal["ok", "empty"]
    entities: list[CulturalEntity]
    scope: Literal["saved_catalogue"] = "saved_catalogue"
    provenance: list[CulturalRequest] = Field(default_factory=list)


class RelatedResult(StrictModel):
    status: Literal["supported", "unknown"]
    source: CulturalEntity | None
    entities: list[CulturalEntity]
    provenance: list[CulturalRequest]


class ConnectionResult(StrictModel):
    status: Literal["supported", "unsupported", "unknown"]
    claim: Literal["affinity", "collaboration", "personality"]
    source: CulturalEntity | None
    target: CulturalEntity | None
    provenance: list[CulturalRequest]
    limitations: str = "Aggregate cultural affinity is not collaboration or an individual personality fact."
    original_story_interpretation: str = ""


class Commitment(StrictModel):
    choice_id: str
    label: str
    confirmed_grants: list[str]


class ProgressResult(StrictModel):
    requested_scope: Literal["all", "inventory", "commitments", "visits", "objectives"] = "all"
    objectives: list[Objective]
    discoveries: list[str]
    commitments: list[Commitment]
    unrecognized_choice_ids: list[str]
    visits_spent: int
    visits_remaining: int
    visit_rules: str
    encounter_id: str
    ending: str
    history_limit: str = (
        "Only saved flags and committed choice IDs confirm events. Absence of a choice does not prove a declined offer."
    )


class DiscoveryResult(StrictModel):
    status: Literal["proposed", "committed", "unavailable"]
    command: Command | None
    proposed_grants: list[str]
    message: str


ARGUMENTS = {
    "search_entities": SearchArguments,
    "get_related_entities": RelatedArguments,
    "inspect_connection": ConnectionArguments,
    "check_progress": ProgressArguments,
    "record_discovery": DiscoveryArguments,
}
PURPOSES = {
    "search_entities": "Find real entities in this run's saved catalogue by query/category; no fresh Qloo search.",
    "get_related_entities": "Read saved outgoing recommendations for an exact known seed UUID, without inventing reverse links.",
    "inspect_connection": "Inspect a named pair or selected pair; distinguish affinity evidence from unsupported collaboration/personality claims.",
    "check_progress": "Answer factual inventory, accepted/declined offers, commitments, past decisions, visits and objective questions from confirmed state, never model memory.",
    "record_discovery": "Record an explicitly requested nearby quest discovery, memory, promise or supported Curator proof through an engine-validated choice. Not ordinary dialogue or hypothetical consent. Extract any explicitly named target into requested_name verbatim, INCLUDING an unknown/unlisted name; empty only for deictic requests like this card.",
}


def snapshot(view):
    # Round-trip revalidation also catches malformed already-constructed nested models.
    return GameState.model_validate(view["state"])


def catalogue(state):
    return {
        str(e.entity_id): e
        for link in (state.cultural_context.links if state.cultural_context else [])
        for e in [link.seed, *link.recommendations]
    }


def discovery_actions(chapter, state):
    result = {}
    view = game_view(chapter, state, "tool-preview", 0)
    for obj in view["nearby"]:
        for choice in obj["choices"]:
            if not choice["grants"]:
                continue
            command = Command(kind="choose", target=obj["id"], choice=choice["id"])
            try:
                changed, _ = apply_command(chapter, state, command)
            except DomainError:
                continue
            if changed.ending == "dawn":
                continue
            result[f"choose:{obj['id']}:{choice['id']}"] = (command, choice)
    return result


def check_progress(chapter, state):
    from .culture import chapter_for_state

    choices = {c.id: c for p in chapter_for_state(chapter, state).locations for o in p.objects for c in o.choices}
    commitments = [
        Commitment(
            choice_id=cid,
            label=choices[cid].label,
            confirmed_grants=[f for f in choices[cid].grants if f in state.flags],
        )
        for cid in state.choices
        if cid in choices
    ]
    return ProgressResult(
        objectives=game_view(chapter, state, "progress", 0)["objectives"],
        discoveries=list(state.flags),
        commitments=commitments,
        unrecognized_choice_ids=[cid for cid in state.choices if cid not in choices],
        visits_spent=state.visits,
        visits_remaining=12 - state.visits,
        visit_rules=state.visit_rules,
        encounter_id=state.encounter_id,
        ending=state.ending,
    )


def execute(chapter, view, tool_id, arguments):
    """Called only after turn ownership/reservation. No model-generated results accepted."""
    if tool_id not in ARGUMENTS:
        raise DomainError("TOOL_UNKNOWN", "That investigation tool is unavailable.", 422)
    args = ARGUMENTS[tool_id].model_validate(arguments)
    state = snapshot(view)
    links = state.cultural_context.links if state.cultural_context else []
    entities = catalogue(state)
    if tool_id == "search_entities":
        found = [
            e
            for e in entities.values()
            if args.query.strip().casefold() in e.name.casefold()
            and (args.category == "any" or e.category == args.category)
        ]
        provenance = []
        ids = {e.entity_id for e in found}
        for link in links:
            for entity, evidence in [
                (link.seed, link.evidence[0]),
                *[(e, link.evidence[1]) for e in link.recommendations],
            ]:
                if entity.entity_id in ids and evidence not in provenance:
                    provenance.append(evidence)
        return SearchResult(status="ok" if found else "empty", entities=found, provenance=provenance)
    if tool_id == "get_related_entities":
        link = next((link for link in links if str(link.seed.entity_id) == str(args.entity_id)), None)
        return RelatedResult(
            status="supported" if link else "unknown",
            source=entities.get(str(args.entity_id)),
            entities=link.recommendations if link else [],
            provenance=link.evidence if link else [],
        )
    if tool_id == "inspect_connection":
        source, target = args.source_id, args.target_id
        # Null/null explicitly means this run's selected pair; never replace a
        # supplied unknown ID with a plausible/default pair.
        if args.pair == "selected" and source is None and target is None and links:
            source, target = links[0].seed.entity_id, links[0].selected_id
        link = next(
            (
                link
                for link in links
                if link.seed.entity_id == source and any(e.entity_id == target for e in link.recommendations)
            ),
            None,
        )
        return ConnectionResult(
            status=("supported" if args.claim == "affinity" else "unsupported") if link else "unknown",
            claim=args.claim,
            source=entities.get(str(source)),
            target=entities.get(str(target)),
            provenance=link.evidence if link else [],
            original_story_interpretation=link.setting if link else "",
        )
    if tool_id == "check_progress":
        return check_progress(chapter, state).model_copy(update={"requested_scope": args.scope})
    actions = discovery_actions(chapter, state)
    if args.action_id not in actions:
        return DiscoveryResult(
            status="unavailable",
            command=None,
            proposed_grants=[],
            message="No such eligible nearby discovery. Nothing was recorded; inspect requirements and try again.",
        )
    command, choice = actions[args.action_id]
    from .culture import chapter_for_state

    target = next(
        o for loc in chapter_for_state(chapter, state).locations for o in loc.objects if o.id == command.target
    )
    # The named target may be the actual addressed resident ("I promise Sera")
    # or the discovery/work itself. Both must be part of this exact command;
    # an unrelated cultural title cannot be substituted.
    requested_name = args.requested_name.casefold().removesuffix("'s").removesuffix("’s")
    if args.requested_name and not (
        requested_name.casefold() in choice["label"].casefold()
        or requested_name.casefold() == target.name.split(" ·")[0].casefold()
    ):
        return DiscoveryResult(
            status="unavailable",
            command=None,
            proposed_grants=[],
            message="The named target does not match that eligible discovery. Nothing was substituted or recorded.",
        )
    return DiscoveryResult(
        status="proposed",
        command=command,
        proposed_grants=choice["grants"],
        message="Eligible proposal only. The owning turn transaction must confirm this choice before it counts as recorded.",
    )


def render(tool_id, result, state):
    if tool_id == "search_entities":
        return "Saved catalogue search: " + (
            "; ".join(f"{e.name} ({e.category})" for e in result.entities)
            or "No saved entity matches. No new provider search was made."
        )
    if tool_id == "get_related_entities":
        return (
            "Saved related entities: "
            + (
                "; ".join(e.name for e in result.entities)
                if result.entities
                else "No supported outgoing recommendations for that entity in this run."
            )
            + " Aggregate affinity only; no reverse relationship is inferred."
        )
    if tool_id == "inspect_connection":
        if result.source and result.target and result.provenance:
            link = next(
                link
                for link in state.cultural_context.links
                if link.seed.entity_id == result.source.entity_id
                and any(e.entity_id == result.target.entity_id for e in link.recommendations)
            )
            # Render the actual requested result, not an unrelated selected card.
            requested = link.model_copy(update={"selected_id": result.target.entity_id, "supporting_tag_id": ""})
            return cultural_evidence_text(requested) + " Requested claim: " + result.claim + " — " + result.status + "."
        return "Saved cultural evidence: no Qloo cultural evidence supports that requested pair. The relationship is unknown; no collaboration or personality claim can be verified."
    if tool_id == "check_progress":
        owned = ", ".join(result.discoveries) or "none"
        commitments = "; ".join(c.label for c in result.commitments)
        if result.unrecognized_choice_ids:
            commitments += f"; {len(result.unrecognized_choice_ids)} saved choice(s) have unavailable labels; their meaning is unverified"
        commitments = commitments.lstrip("; ") or "none"
        missing = "; ".join(o.label for o in result.objectives if not o.completed)
        unearned = ", ".join(o.id for o in result.objectives if not o.completed) or "none"
        return f"Confirmed progress: Inventory/discoveries: {owned}. Not yet acquired/completed: {unearned}. Recorded commitments: {commitments}. Visits spent: {result.visits_spent}/12. Ending: {result.ending or 'not reached'}. Unfinished: {missing}. No unrecorded acceptance, refusal or declined offer can be inferred."
    return result.message
