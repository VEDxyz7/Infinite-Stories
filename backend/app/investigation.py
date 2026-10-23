"""Versioned cultural investigation, derived solely from validated saved entities."""

from .models import Choice, WorldObject

VERSION = "cultural-investigation-v2"


def enabled(state):
    return state.cultural_context is not None and state.cultural_context.rule_version in (
        VERSION,
        "cultural-understanding-v3",
    )


def furnish(chapter):
    patterns = {
        "quay": [(x, y) for x in (19, 22) for y in (12, 13)],
        "market": [(x, y) for x in (17, 19, 21, 23) for y in (11, 13)],
        "archive": [(x, y) for x in (18, 21, 24) for y in (12, 13)],
        "station": [(18, y) for y in (11, 12, 13)],
    }
    for location in chapter.locations:
        rows = [list(row) for row in location.rows]
        for x, y in patterns[location.id]:
            rows[y][x] = "1"
        location.rows = ["".join(row) for row in rows]


def decorate(chapter, state):
    if not enabled(state):
        return
    furnish(chapter)
    cinema = next(p for p in chapter.locations if p.id == "market")
    gate = next(o for p in chapter.locations for o in p.objects if o.id == "beacon")
    traces, proofs = [], []
    order = state.city_generation.proof_order if state.city_generation else range(len(state.cultural_context.links))
    next_proof = next((i for i in order if f"proof_{i}" not in state.flags), None)
    for i, link in enumerate(state.cultural_context.links):
        entity = next(e for e in link.recommendations if e.entity_id == link.selected_id)
        traces.append(f"trace_{i}")
        proofs.append(f"proof_{i}")
        cinema.objects.append(
            WorldObject(
                id=f"screening_note_{i}",
                name=f"Screening note · {link.seed.name}",
                kind="object",
                x=12 + i * 3,
                y=6,
                text=f"Ivo left a question: which returned {entity.category} connects to {link.seed.name}? Use the Scanner's saved results. A recommendation supports affinity, not a collaboration or a fact about a person.",
                choices=[
                    Choice(
                        id=f"trace_{i}_{entity.entity_id}",
                        label=f"Record affinity: {entity.name}",
                        requires=["map"],
                        grants=[f"trace_{i}"],
                        text=f"The saved Qloo result includes {entity.name} for {link.seed.name}. Ivo accepts the screening note; this establishes affinity only.",
                    ),
                    Choice(
                        id=f"hypothesis_screen_{i}",
                        label="Claim this proves a collaboration",
                        requires=["map"],
                        text="Unsupported hypothesis.",
                    ),
                ],
            )
        )
        if i == next_proof:
            gate.choices.insert(
                0,
                Choice(
                    id=f"prove_{i}_{entity.entity_id}",
                    label=f"Present saved affinity: {link.seed.name} → {entity.name}",
                    requires=["map", "rhythm", "chronicle", f"culture_{i}"],
                    grants=[f"proof_{i}"],
                    text=f"The Curator verifies the saved entity identifiers: {link.seed.name} → {entity.name}. Affinity accepted; no collaboration or personality claim is established.",
                ),
            )
    for obj in cinema.objects:
        if obj.id == "ivo":
            for choice in obj.choices:
                choice.requires.extend(traces)
    if next_proof is not None:
        gate.choices.insert(
            1,
            Choice(
                id="hypothesis_curator",
                label="Claim affinity reveals my personality",
                requires=["map", "rhythm", "chronicle"],
                text="Unsupported hypothesis.",
            ),
        )
    for choice in gate.choices:
        if choice.ending:
            choice.requires.extend([f"proof_{i}" for i in order])
