"""Deterministic original quest content from validated Qloo evidence; no provider calls."""

from .content import validate_chapter
from .investigation import decorate, enabled
from .models import Choice, WorldObject
from .presentation import dress_chapter

SETTINGS = {
    "urn:tag:theme:qloo:art_and_creativity": (
        "Paper theater",
        "Fold a paper stage where the city's memories can be rehearsed.",
    ),
    "urn:tag:keyword:media:hidden_door": (
        "Hidden-door archive",
        "Find the little door behind a shelf of unclaimed stories.",
    ),
    "urn:tag:artist:qloo:experimental": (
        "Experimental echo chamber",
        "Arrange the resonating shells until their echoes form a path.",
    ),
    "urn:tag:theme:qloo:change": ("Shifting archive", "Rearrange the movable shelves to carry a memory safely onward."),
    "urn:tag:theme:qloo:growing_up": (
        "Growing archive",
        "Choose what the city's younger storytellers should carry forward.",
    ),
    "urn:tag:interests:qloo:wildlife_conservation": (
        "Conservation mural",
        "Restore an original mural of the creatures that share the quay.",
    ),
}


def select_setting(seed, entities):
    preferred = list(SETTINGS)
    if seed.category == "videogame":
        preferred.insert(0, "urn:tag:interests:qloo:wildlife_conservation")
    for tag in preferred:
        for entity in entities:
            if tag in {t.id for t in entity.tags}:
                return entity.entity_id, SETTINGS[tag][0], tag
    return entities[0].entity_id, "Archive of echoes", ""


def chapter_for_state(base, state):
    chapter = base.model_copy(deep=True)
    if state.cultural_context is None:
        return dress_chapter(chapter, state)
    chapter.source = "qloo_informed"
    archive = next(loc for loc in chapter.locations if loc.id == "archive")
    requirements = []
    for i, link in enumerate(state.cultural_context.links):
        selected = next(e for e in link.recommendations if e.entity_id == link.selected_id)
        flag = f"culture_{i}"
        requirements.append(flag)
        creative = SETTINGS.get(
            link.supporting_tag_id, ("Archive of echoes", "Choose a cultural card to carry to the keeper.")
        )[1]
        archive.objects.append(
            WorldObject(
                id=f"cultural_echo_{i}",
                name=link.setting,
                kind="object",
                x=12 + i * 3,
                y=6,
                text=f"{creative} Qloo recommended {selected.name} for {link.seed.name}. This setting is an original story interpretation, not a factual connection.",
                choices=[
                    Choice(
                        id=f"echo_{i}_" + str(selected.entity_id),
                        label="Carry the card: " + selected.name,
                        requires=["rhythm"],
                        grants=[flag],
                        text=(
                            f"You carry the {selected.name} card to Sera. Its saved affinity is ready for her chronicle; your promise is still needed."
                            if enabled(state)
                            else f"You carry the {selected.name} card to Sera. A new memory joins the chronicle."
                        ),
                    )
                ],
            )
        )
    for obj in archive.objects:
        if obj.id == "sera":
            obj.text = "Bring the cultural memory cards, then choose the promise that will open the station."
            for choice in obj.choices:
                choice.requires.extend(requirements)
    archive.description = "A chamber of cultural echoes, shaped by your selected interests and Qloo recommendations."
    decorate(chapter, state)
    validate_chapter(chapter)
    return dress_chapter(chapter, state)


def cultural_evidence_text(link):
    """Render only validated saved fields; no inference, requests or creative facts."""
    entity = next(e for e in link.recommendations if e.entity_id == link.selected_id)
    tags = [t.name for t in entity.tags if t.id == link.supporting_tag_id]
    tags += [t.name for t in entity.tags if t.name not in tags]
    metadata = (" Recorded recommendation tags: " + ", ".join(tags[:2]) + ".") if tags else ""
    return (
        f"Saved Qloo evidence (server-rendered): {link.seed.name} ({link.seed.category}) "
        f"→ {entity.name} ({entity.category})."
        + metadata
        + f" Original story setting: {link.setting}; this is our creative interpretation, not a Qloo fact. "
        "The recommendation represents aggregate cultural affinity, not proof of collaboration or partnership, "
        "and does not reveal your individual personality."
    )
