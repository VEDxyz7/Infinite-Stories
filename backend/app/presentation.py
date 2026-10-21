"""Authored venue presentation. Reads confirmed progress; never invents provider facts."""

VENUES = {
    "quay": (
        "Side A · Lantern Quay",
        "Needle hiss and amber lamps spill from Side A. Mara is keeping the last record playing.",
    ),
    "market": (
        "Afterimage · Night Market",
        "Afterimage's projector throws a silver path across the rain. Ivo is waiting by the screening floor.",
    ),
    "archive": (
        "Thread & Echo · House of Echoes",
        "Garment labels, sealed letters and cultural memory cards line Sera's boutique. Nothing here is taken without consent.",
    ),
    "station": (
        "The Last Gate · Dawn Station",
        "Three memory sockets frame the dawn tram. The Curator waits for your decision, not a password.",
    ),
}


def resident_text(object_id, state):
    flags = set(state.flags)
    investigation = (
        state.cultural_context is not None and state.cultural_context.rule_version == "cultural-investigation-v2"
    )
    if object_id == "mara":
        if investigation and "map" not in flags:
            favourites = ", ".join(link.seed.name for link in state.cultural_context.links)
            return f"Mara lifts the needle. 'You brought {favourites} into the city. Ivo can test the saved cultural echoes at Afterimage; a recommendation is a thread, not a verdict about you. Take the map from my record sleeve. The east arch leads to his cinema; the gate needs a way home, a rhythm and a promise.'"
        if "map" in flags:
            return "Mara slides a record back into its sleeve. 'Keep that map dry. Ivo runs Afterimage, through the east arch. He can turn a route into a rhythm.'"
        return "Mara lifts the needle. 'A good B-side knows a way home. Take the map from my record sleeve; then find Ivo at Afterimage, east of here. The gate needs a way home, a rhythm and a promise.'"
    if object_id == "ivo":
        if (
            investigation
            and "map" in flags
            and any(f"trace_{i}" not in flags for i in range(len(state.cultural_context.links)))
        ):
            return "Ivo taps an empty film can. 'I label evidence, not hunches. Inspect the screening notes by the street; Search and Related in your Scanner show the saved catalogue. Record each supported result, then I will teach you the rhythm. Looking and wrong answers cost no visits.'"

        if "rhythm" in flags:
            return "Ivo lets the final frame linger. 'You have the projector's rhythm now. East again: Sera keeps Thread & Echo. Listen before you decide what to carry out of this city.'"
        if "map" not in flags:
            return "Ivo peers through a strip of film. 'Every screening needs a route back to the audience. Bring Mara's map from Side A first; the west arch takes you there.'"
        return "Ivo threads a reel. 'Mara's map? Good. Hear that shutter: light, dark, light. Trade me the story of your route, and I'll teach you the rhythm Sera is waiting for.'"
    if object_id == "sera":
        if "chronicle" in flags:
            promise = "the private letters stay sealed" if "guarding" in flags else "the willing voices travel with you"
            return f"Sera knots a ribbon around the chronicle. 'We agreed: {promise}. Your promise is yours to keep. The Curator waits through the east arch.'"
        if "rhythm" not in flags:
            return "Sera straightens a handmade label. 'A brand is a story someone chose to wear; it is not a verdict about a person. Hear Ivo's rhythm at Afterimage before we choose a promise.'"
        missing = (
            sum(f"culture_{i}" not in flags for i, _ in enumerate(state.cultural_context.links))
            if state.cultural_context
            else 0
        )
        if missing:
            return f"Sera opens an empty display case. 'We still need {missing} cultural memory card(s). They are on the street in front of this boutique. Inspect a card, or open the Scanner for its saved Qloo evidence. Then return and choose your promise.'"
        return "Sera lays out two ribbons. 'The chronicle is ready. Will you share the city's stories, or protect its private letters? Neither promise belongs to a recommendation. This part is your choice.'"
    if object_id == "beacon":
        missing = [
            name
            for flag, name in (("map", "Mara's way home"), ("rhythm", "Ivo's rhythm"), ("chronicle", "Sera's promise"))
            if flag not in flags
        ]
        if missing:
            return (
                "The Curator rests a hand beside the unlit sockets. 'The gate does not judge your taste. Bring "
                + ", ".join(missing)
                + ". You can return through the west arch.'"
            )
        if investigation:
            pending = next(
                (link for i, link in enumerate(state.cultural_context.links) if f"proof_{i}" not in flags), None
            )
            if pending is not None:
                return f"The Curator studies your chronicle. 'Your next claim concerns {pending.seed.name}. Present the saved cross-category affinity. A beautiful invented explanation is not evidence. The Scanner holds the actual returned identifiers; your privacy promise remains your choice.'"
        return "The Curator steps aside. 'All three memories are here. Wake the tram and leave together, or open the gate and stay to tend its light. A different ending is not a lesser one.'"
    return None


def dress_chapter(chapter, state):
    for location in chapter.locations:
        location.name, location.description = VENUES.get(location.id, (location.name, location.description))
        for obj in location.objects:
            text = resident_text(obj.id, state)
            if text is not None:
                obj.text = text
    return chapter
