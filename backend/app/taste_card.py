"""Versioned, deterministic completion reward. No model, provider or network calls."""

from collections import Counter

from .models import TasteCard, TasteRelationship

DISCOVERIES = {
    "map": "Mara's way home",
    "rhythm": "Ivo's rhythm",
    "chronicle": "Sera's chronicle",
    "guarding": "Chose to protect private letters",
    "sharing": "Chose to share the city's stories",
    "kindness": "Relit the market lantern",
    "control_trace": "Synthetic screening motif: three amber circles",
    "control_memory": "Synthetic memory: the invented film's matching motif",
    "control_proof": "Solved the authored motif puzzle (not cultural affinity)",
}


def build(state):
    """Only confirmed flags mean encountered/discovered; catalogue reads aren't receipts."""
    flags = set(state.flags)
    discoveries = [label for flag, label in DISCOVERIES.items() if flag in flags]
    encountered, relationships = {}, []
    links = state.cultural_context.links if state.cultural_context else []
    favourites = {str(i.entity_id) for i in state.interests if i.entity_id}
    favourites.update(str(link.seed.entity_id) for link in links)
    for i, link in enumerate(links):
        encountered[str(link.seed.entity_id)] = link.seed
        selected = next(e for e in link.recommendations if e.entity_id == link.selected_id)
        if any(f"{stage}_{i}" in flags for stage in ("trace", "culture", "proof")):
            encountered[str(selected.entity_id)] = selected
            relationships.append(
                TasteRelationship(
                    source=link.seed,
                    target=selected,
                    provenance=link.evidence,
                    explanation="Returned in saved cross-category recommendations: aggregate affinity, not collaboration or personal identity.",
                )
            )
            discoveries.append(f"{link.seed.name} → {selected.name}: saved affinity inspected")
    encountered = dict(sorted(encountered.items()))
    categories = sorted({e.category for e in encountered.values()})
    tags = Counter(t.id for e in encountered.values() for t in {t.id: t for t in e.tags}.values())
    names = {t.id: t.name for e in encountered.values() for t in e.tags}
    labels = [names[t] for t in sorted(tags, key=lambda t: (-tags[t], t))[:3]]
    if state.generic_control:
        profile = "Lantern storyteller"
        milestones = sum(flag in flags for flag in ("control_trace", "control_memory", "control_proof"))
        basis = f"Authored demo profile: {milestones}/3 motif milestones confirmed, plus saved story choices. No cultural taste was measured."
    elif relationships:
        directions = {r.source.category for r in relationships}
        profile = (
            {
                "artist": "Sound-to-screen explorer",
                "movie": "Screen-to-sound explorer",
                "brand": "Design-to-screen explorer",
                "videogame": "Play-to-screen explorer",
            }.get(next(iter(directions)), "Cross-media explorer")
            if len(directions) == 1
            else "Cross-media explorer"
        )
        basis = (
            f"Application heuristic v1: {len(relationships)} confirmed saved recommendation thread(s) across "
            + ", ".join(categories)
            + ". This describes this run's exploration, not personality or an official Qloo classification."
        )
    else:
        profile = "First-light explorer"
        basis = "Application heuristic v1: no cultural thread was confirmed before this ending; insufficient evidence for a cultural taste classification."
    if labels:
        basis += " Available encountered-entity tags, ranked by entity count then tag ID: " + ", ".join(labels) + "."
    elif links:
        basis += " Comparable tag detail is unavailable; no genre preference is inferred."
    # Exclude all favourites (even another seed's recommendation), confirmed
    # discoveries and duplicate UUIDs. Stable source/target ordering is reproducible.
    candidates = {}
    for link in sorted(links, key=lambda link: str(link.seed.entity_id)):
        for entity in sorted(link.recommendations, key=lambda entity: str(entity.entity_id)):
            eid = str(entity.entity_id)
            if eid in favourites or eid in encountered:
                continue
            candidates.setdefault(
                eid,
                TasteRelationship(
                    source=link.seed,
                    target=entity,
                    provenance=link.evidence,
                    explanation=f"Returned for {link.seed.name} in this run's saved recommendations; not yet a confirmed discovery. Aggregate affinity only.",
                ),
            )
    recommendations = list(candidates.values())[:6]
    return TasteCard(
        domain="qloo" if links else "invented_demo" if state.generic_control else "authored",
        ending=state.ending,
        favourites=[
            {"name": link.seed.name, "category": link.seed.category, "entity_id": link.seed.entity_id} for link in links
        ]
        if links
        else state.interests,
        discoveries=discoveries,
        encountered=list(encountered.values()),
        relationships=relationships,
        profile=profile,
        profile_basis=basis,
        metadata_labels=labels,
        try_next=recommendations,
        recommendations_note=(
            "Saved recommendations only; not new provider requests. These entities were not confirmed as discoveries during this run."
            if recommendations
            else "No additional supported, undiscovered recommendations are available in this save."
        ),
    )


def complete(state):
    if state.ending and state.taste_card is None:
        state.taste_card = build(state)
    return state
