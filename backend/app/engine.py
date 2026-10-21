import math

from .content import current_location, walkable
from .culture import chapter_for_state
from .investigation import enabled
from .models import Chapter, Command, DomainError, GameState, GameView


def apply_command(chapter: Chapter, original: GameState, command: Command) -> tuple[GameState, str]:
    chapter = chapter_for_state(chapter, original)
    state = original.model_copy(deep=True)
    if state.ending:
        raise DomainError("STORY_COMPLETE", "This chapter has concluded. Start a new journey to choose another path.")
    loc = current_location(chapter, state)
    if command.kind == "position":
        distance = math.hypot(command.x - state.x, command.y - state.y)
        if distance > 4:
            raise DomainError("MOVE_TOO_FAR", "Movement must follow a nearby walkable path.")
        steps = max(1, math.ceil(distance / 0.15))
        if any(
            not walkable(loc, state.x + (command.x - state.x) * i / steps, state.y + (command.y - state.y) * i / steps)
            for i in range(steps + 1)
        ):
            raise DomainError("BLOCKED_PATH", "That path crosses solid terrain.")
        state.x, state.y = command.x, command.y
        return state, "Position saved."
    obj = next((obj for obj in loc.objects if obj.id == command.target), None)
    if obj is None:
        raise DomainError("OBJECT_UNAVAILABLE", "That object is not in your current area.")
    if math.hypot(state.x - obj.x, state.y - obj.y) > 2.0:
        raise DomainError("OUT_OF_REACH", "Move closer to interact.")
    if command.kind in ("interact", "inspect"):
        narrative = obj.text
    elif command.kind == "travel":
        if obj.kind != "portal":
            raise DomainError("INVALID_PORTAL", "That object is not an exit.")
        if state.visits >= 12:
            state.ending = "dawn"
            narrative = "Dawn reaches the city before you reach the tram. You will keep these unfinished stories until another night."
        else:
            state.location_id = obj.destination
            state.x, state.y = (3, 8) if obj.id.endswith("_east") else (28, 8)
            state.visits += 1
            narrative = next(loc.description for loc in chapter.locations if loc.id == obj.destination)
    elif command.kind == "choose":
        if (
            enabled(state)
            and command.choice.startswith("hypothesis_")
            and any(c.id == command.choice for c in obj.choices)
        ):
            raise DomainError(
                "EVIDENCE_UNSUPPORTED",
                "Saved Qloo recommendations support aggregate affinity, not collaboration or a personality claim. Inspect the actual connection and try again; no visit was spent.",
            )
        choice = next((c for c in obj.choices if c.id == command.choice), None)
        if choice is None or not set(choice.requires) <= set(state.flags):
            raise DomainError("PREREQUISITE_MISSING", "That choice is not currently available.")
        if choice.id in state.choices:
            raise DomainError("ALREADY_CHOSEN", "That choice has already been made.")
        if obj.id == "sera" and "chronicle" in state.flags:
            raise DomainError("CHOICE_COMMITTED", "The keeper already entrusted you with the chronicle.")
        state.flags = sorted(set(state.flags) | set(choice.grants))
        state.choices.append(choice.id)
        state.ending = choice.ending
        narrative = choice.text
        if state.ending and "kindness" in state.flags:
            narrative += " Behind you, the market lantern stays alight."
        if state.ending and "guarding" in state.flags:
            narrative += " The private letters remain sealed."
    else:
        raise DomainError("ACTION_UNSUPPORTED", "That action cannot be applied.")
    state.history = (state.history + [narrative])[-50:]
    return state, narrative


def game_view(chapter: Chapter, state: GameState, session_id: str, revision: int, narrative: str = ""):
    chapter = chapter_for_state(chapter, state)
    loc = current_location(chapter, state)
    nearby = []
    for obj in loc.objects:
        if math.hypot(state.x - obj.x, state.y - obj.y) <= 2:
            item = obj.model_dump()
            item["choices"] = [
                c.model_dump()
                for c in obj.choices
                if set(c.requires) <= set(state.flags)
                and c.id not in state.choices
                and not (obj.id == "sera" and "chronicle" in state.flags)
            ]
            nearby.append(item)
    cultural_objectives = (
        [
            {
                "id": f"culture_{i}",
                "label": "Carry the cultural memory for " + link.seed.name,
                "completed": f"culture_{i}" in state.flags,
            }
            for i, link in enumerate(state.cultural_context.links)
        ]
        if state.cultural_context
        else []
    )
    if enabled(state):
        cultural_objectives += [
            {
                "id": f"{stage}_{i}",
                "label": (
                    "Trace the screening connection for "
                    if stage == "trace"
                    else "Prove saved affinity to the Curator: "
                )
                + link.seed.name,
                "completed": f"{stage}_{i}" in state.flags,
            }
            for stage in ("trace", "proof")
            for i, link in enumerate(state.cultural_context.links)
        ]
    result = {
        "schema_version": 1,
        "session_id": session_id,
        "revision": revision,
        "state": state.model_dump(mode="json"),
        "location": loc.model_dump(),
        "nearby": nearby,
        "objectives": cultural_objectives
        + [
            {"id": flag, "label": label, "completed": flag in state.flags}
            for flag, label in [
                ("map", "Find a way home with Mara at Lantern Quay"),
                ("rhythm", "Learn Ivo's rhythm in the Night Market"),
                ("chronicle", "Make a promise to Sera in the House of Echoes"),
                ("beacon", "Choose the last beacon's future at Dawn Station"),
            ]
        ],
        "narrative": narrative,
        "idempotent_replay": False,
        "notices": (
            [
                "Qloo recommendations shaped the required cultural quests. Story settings are original interpretations, not facts about you."
            ]
            if state.mode == "cultural"
            else ["Original authored chapter. This journey uses no cultural-service data."]
        ),
    }
    return GameView.model_validate(result).model_dump(mode="json")
