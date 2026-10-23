"""Saved-data city plans. Tag contrast is our heuristic, never a Qloo score."""

import hashlib
import json
from collections import deque

from .models import CityGeneration, CulturalDistance

VENUES = ("quay", "market", "archive")


def stable(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def distance(seed, target):
    # Compare IDs only within tag domains present on BOTH entities. Disjoint
    # schemas are missing comparable metadata, not evidence of maximal distance.
    domains = sorted({t.type for t in seed.tags if t.type} & {t.type for t in target.tags if t.type})
    left = {t.id for t in seed.tags if t.type in domains}
    right = {t.id for t in target.tags if t.type in domains}
    union = left | right
    return CulturalDistance(
        source_id=seed.entity_id,
        target_id=target.entity_id,
        comparable_domains=domains,
        shared_tags=sorted(left & right),
        contrast=round(1 - len(left & right) / len(union), 6) if union else None,
        metadata_status="comparable" if union else "unknown",
    )


def evidence_paths(context, source, target):
    """Only exact directed saved edges; max two hops, no affinity transitivity claim."""
    graph = {}
    for link in context.links:
        graph.setdefault(str(link.seed.entity_id), set()).update(str(e.entity_id) for e in link.recommendations)
    queue = deque([[str(source)]])
    found = []
    while queue:
        path = queue.popleft()
        if len(path) > 1 and path[-1] == str(target):
            found.append(path)
            continue
        if len(path) < 3:
            for nxt in sorted(graph.get(path[-1], [])):
                if nxt not in path:
                    queue.append([*path, nxt])
    return found[:6]


def generate(context, attempt, seed=None):
    """Choose a candidate without mutating/fetching evidence. Three attempts upstream."""
    from .culture import select_setting

    result = context.model_copy(deep=True)

    def canonical(entity):
        value = entity.model_dump(mode="json")
        value["tags"] = sorted(value["tags"], key=lambda tag: (tag["id"], tag["type"], tag["name"]))
        return value

    catalogue = sorted(
        [
            {
                "seed": canonical(link.seed),
                "results": sorted((canonical(e) for e in link.recommendations), key=lambda e: e["entity_id"]),
            }
            for link in context.links
        ],
        key=lambda row: row["seed"]["entity_id"],
    )
    seed = seed or stable(catalogue)
    signature = stable([seed, attempt])
    variant = int(signature[:8], 16) % 3
    measures = []
    favourites = {link.seed.entity_id for link in result.links}
    for i, link in enumerate(result.links):
        ranked = sorted(
            (entity for entity in link.recommendations if entity.entity_id not in favourites),
            key=lambda e: (
                -(distance(link.seed, e).contrast if distance(link.seed, e).contrast is not None else -1),
                stable([seed, str(e.entity_id)]),
            ),
        )
        if not ranked:
            raise ValueError("Saved recommendations contain no entity outside the selected favourites")
        selected = ranked[attempt % len(ranked)]
        link.selected_id, link.setting, link.supporting_tag_id = select_setting(link.seed, [selected])
        if not link.supporting_tag_id and selected.tags:
            link.supporting_tag_id = sorted(t.id for t in selected.tags)[0]
        measure = distance(link.seed, selected).model_dump(mode="json")
        measure.update(
            relationship="direct_saved_recommendation",
            paths=evidence_paths(result, link.seed.entity_id, selected.entity_id),
        )
        measures.append(CulturalDistance.model_validate(measure))
    order = sorted(
        range(len(result.links)),
        key=lambda i: (
            -(measures[i].contrast if measures[i].contrast is not None else -1),
            stable([seed, str(result.links[i].seed.entity_id)]),
        ),
    )
    # Three distinct investigation routes; all existing street arches remain.
    traces = [["market"], ["quay", "archive"], ["archive", "quay", "market"]][variant]
    cards = [["archive"], ["market", "quay"], ["quay", "market", "archive"]][variant]
    plan = CityGeneration(
        seed=seed,
        candidate=attempt,
        template=variant,
        proof_order=order,
        trace_locations=[traces[n % len(traces)] for n in range(len(order))],
        card_locations=[cards[n % len(cards)] for n in range(len(order))],
        resident_links={
            "mara": order[0],
            "ivo": order[-1],
            "sera": order[1 + variant % (len(order) - 2)] if len(order) > 2 else order[variant % len(order)],
        },
        distances=measures,
        shortcut=(["quay", "archive"] if variant == 1 else ["market", "station"] if variant == 2 else []),
    )
    return result, plan


def apply_plan(chapter, state):
    plan = state.city_generation
    if plan is None or state.cultural_context.rule_version != "cultural-understanding-v3":
        return
    locations = {loc.id: loc for loc in chapter.locations}
    for ordinal, i in enumerate(plan.proof_order):
        for prefix, destination, y in (
            ("screening_note_", plan.trace_locations[ordinal], 6),
            ("cultural_echo_", plan.card_locations[ordinal], 4),
        ):
            owner = next(loc for loc in chapter.locations if any(o.id == prefix + str(i) for o in loc.objects))
            obj = next(o for o in owner.objects if o.id == prefix + str(i))
            owner.objects.remove(obj)
            obj.x, obj.y = 6 + ordinal * 3, y
            locations[destination].objects.append(obj)
            # Trace/card edges are real GAME dependencies, not invented Qloo links.
            for choice in obj.choices:
                if choice.grants and prefix == "cultural_echo_":
                    choice.requires.append(f"trace_{i}")
                if choice.grants and ordinal and plan.template:
                    previous = state.cultural_context.links[plan.proof_order[ordinal - 1]]
                    obj.text += f" Route prerequisite: first collect the {'screening note' if prefix == 'screening_note_' else 'memory card'} for {previous.seed.name}. This is an investigation step, not an extra Qloo relationship."
                    choice.requires.append(
                        ("trace_" if prefix == "screening_note_" else "culture_") + str(plan.proof_order[ordinal - 1])
                    )
    if plan.shortcut:
        from .models import WorldObject

        for source, dest in (plan.shortcut, plan.shortcut[::-1]):
            locations[source].objects.append(
                WorldObject(
                    id=source + "_passage",
                    name="Lantern passage",
                    kind="portal",
                    x=26,
                    y=6,
                    destination=dest,
                    text="A city passage. Walking through costs no visit.",
                )
            )
    for resident, index in plan.resident_links.items():
        obj = next(o for loc in chapter.locations for o in loc.objects if o.id == resident)
        link = state.cultural_context.links[index]
        obj.text += f" My cultural thread begins with {link.seed.name}."
