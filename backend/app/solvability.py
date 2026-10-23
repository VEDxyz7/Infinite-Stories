"""Bounded executable solution witnesses, using only normalized saved evidence.

No model/provider access. Geometry supplies routes; the real engine validates
EVERY movement, prerequisite, proof and ending. Fail closed on search exhaustion.
"""

import hashlib
import json
from collections import deque

from .content import current_location, walkable
from .culture import chapter_for_state, select_setting
from .engine import apply_command
from .models import ActivationValidation, Command, DomainError, GameState

MAX_CANDIDATES = 3
MAX_GOALS = 128


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def walk(base, state, target, commands):
    loc = current_location(chapter_for_state(base, state), state)
    start = (round(state.x), round(state.y))
    goal = (round(target.x), round(target.y))
    queue, paths = deque([start]), {start: []}
    while queue:
        point = queue.popleft()
        if point == goal:
            for x, y in paths[point]:
                command = Command(kind="position", x=x, y=y)
                state, _ = apply_command(base, state, command)
                commands.append(command.model_dump(mode="json"))
                if state.ending:
                    raise ValueError("Deadline reached on route")
            return state
        for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
            nxt = point[0] + dx, point[1] + dy
            if nxt not in paths and walkable(loc, *nxt):
                paths[nxt] = paths[point] + [nxt]
                queue.append(nxt)
    raise ValueError("Unreachable clue")


def navigate(base, state, destination, commands):
    chapter = chapter_for_state(base, state)
    queue, paths = deque([state.location_id]), {state.location_id: []}
    while queue:
        lid = queue.popleft()
        if lid == destination:
            for portal in paths[lid]:
                state = walk(base, state, portal, commands)
                command = Command(kind="travel", target=portal.id)
                state, _ = apply_command(base, state, command)
                commands.append(command.model_dump(mode="json"))
                if state.ending:
                    raise ValueError("Deadline reached during travel")
            return state
        loc = next(p for p in chapter.locations if p.id == lid)
        for obj in loc.objects:
            if obj.kind == "portal" and obj.destination not in paths:
                paths[obj.destination] = paths[lid] + [obj]
                queue.append(obj.destination)
    raise ValueError("Unreachable venue")


def solve(base, initial):
    """Goal-directed monotone planner; conservative rejection if no witness found.

    Rebuild choices after each grant (including sequential Curator proofs).
    Bound recursion/work independently from the three candidate attempts.
    """
    state = initial.model_copy(deep=True)
    commands, active = [], set()
    work = 0

    def obtain(flag):
        nonlocal state, work
        if flag in state.flags:
            return
        work += 1
        if work > MAX_GOALS or flag in active:
            raise ValueError("Cyclic or excessive dependencies")
        active.add(flag)
        choices = [
            (loc.id, obj.id, choice.id, choice.requires)
            for loc in chapter_for_state(base, state).locations
            for obj in loc.objects
            for choice in obj.choices
            if flag in choice.grants and choice.id not in state.choices
        ]
        if not choices:
            raise ValueError("Missing prerequisite: " + flag)
        # Authored alternatives (e.g. privacy promise) share the same required
        # grant. Try each against an independent state, never retain failed work.
        before, prefix = state.model_copy(deep=True), list(commands)
        parent_active = set(active)
        for lid, oid, cid, requires in choices:
            try:
                state = before.model_copy(deep=True)
                active.clear()
                active.update(parent_active)
                commands[:] = prefix
                for required in requires:
                    obtain(required)
                state = navigate(base, state, lid, commands)
                obj = next(o for p in chapter_for_state(base, state).locations for o in p.objects if o.id == oid)
                state = walk(base, state, obj, commands)
                command = Command(kind="choose", target=oid, choice=cid)
                from .understanding import required, witness

                choice = next(c for c in obj.choices if c.id == cid)
                assessment = witness(state, oid, cid) if required(state, oid, choice) else None
                state, _ = apply_command(base, state, command, understanding=assessment)
                commands.append(command.model_dump(mode="json"))
                if flag not in state.flags or state.ending == "dawn":
                    raise ValueError("Unconfirmed outcome")
                active.remove(flag)
                return
            except (DomainError, ValueError):
                continue
        active.discard(flag)
        raise ValueError("No executable path for " + flag)

    # The actual ending grants beacon; never accept narrated or partial proof.
    obtain("beacon")
    if state.ending not in ("together", "keeper"):
        raise ValueError("No success ending")
    if state.cultural_context:
        for i, link in enumerate(state.cultural_context.links):
            if link.seed.category == next(e.category for e in link.recommendations if e.entity_id == link.selected_id):
                raise ValueError("Not cross-category")
            if (
                state.cultural_context.rule_version in ("cultural-investigation-v2", "cultural-understanding-v3")
                and f"proof_{i}" not in state.flags
            ):
                raise ValueError("Missing verified proof")
    return commands, state


def initial_chapter_fingerprint(base, state):
    """Initial generated world, independent of mutable progress and proof visibility."""
    initial = state.model_copy(
        update={"flags": [], "choices": [], "understanding_records": [], "ending": "", "encounter_id": "", "visits": 0}
    )
    chapter = chapter_for_state(base, initial)
    # Bind the actual puzzle, not cosmetic copy. Future presentation-only edits
    # must not invalidate an otherwise identical saved investigation.
    return fingerprint(
        {
            "visit_rules": initial.visit_rules,
            "locations": [
                {
                    "id": loc.id,
                    "width": loc.width,
                    "height": loc.height,
                    "rows": loc.rows,
                    "objects": [
                        {
                            "id": obj.id,
                            "kind": obj.kind,
                            "x": obj.x,
                            "y": obj.y,
                            "destination": obj.destination,
                            "choices": [
                                {
                                    "id": choice.id,
                                    "requires": choice.requires,
                                    "grants": choice.grants,
                                    "ending": choice.ending,
                                }
                                for choice in obj.choices
                            ],
                        }
                        for obj in loc.objects
                    ],
                }
                for loc in chapter.locations
            ],
        }
    )


def activate_candidate(base, initial):
    """Fetch once elsewhere, then at most three deterministic saved-data candidates."""
    # Revalidate nested models too: an injected/mutated provider cannot bypass
    # provenance or nonempty evidence invariants with an already-built model.
    initial = GameState.model_validate(initial.model_dump(mode="json"))
    for attempt in range(MAX_CANDIDATES):
        candidate = initial.model_copy(deep=True)
        try:
            if (
                candidate.visit_rules == "conversation-v1"
                and candidate.cultural_context
                and candidate.cultural_context.rule_version == "cultural-understanding-v3"
            ):
                from .city_generation import generate

                candidate.cultural_context, candidate.city_generation = generate(
                    initial.cultural_context,
                    attempt,
                    initial.city_generation.seed if initial.city_generation else None,
                )
            elif candidate.cultural_context and attempt:
                for link in candidate.cultural_context.links:
                    entity = link.recommendations[attempt % len(link.recommendations)]
                    link.selected_id, link.setting, link.supporting_tag_id = select_setting(link.seed, [entity])
            commands, final = solve(base, candidate)
            candidate.activation_validation = ActivationValidation.model_validate(
                {
                    "version": "engine-witness-v1",
                    "candidate": attempt,
                    "evidence_sha256": fingerprint(
                        candidate.cultural_context.model_dump(mode="json") if candidate.cultural_context else None
                    ),
                    "chapter_sha256": fingerprint(base.model_dump(mode="json")),
                    "generation_sha256": fingerprint(candidate.city_generation.model_dump(mode="json"))
                    if candidate.city_generation
                    else None,
                    "generated_chapter_sha256": initial_chapter_fingerprint(base, candidate)
                    if candidate.city_generation
                    else None,
                    "commands_sha256": fingerprint(commands),
                    "steps": len(commands),
                    "visits": final.visits,
                    "ending": final.ending,
                }
            )
            return candidate
        except (ValueError, DomainError):
            continue
    raise DomainError(
        "CITY_UNSOLVABLE",
        "No suitable solution was found in three saved-evidence city candidates. Recommendations may lack a new cultural thread or a valid route. No run was activated. Resume your saved journey or choose different favourites.",
        503,
    )
