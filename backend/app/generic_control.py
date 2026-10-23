"""One explicitly synthetic, reproducible control investigation. Never Qloo evidence."""

from .models import Choice, WorldObject


def decorate(chapter, state):
    control = state.generic_control
    places = {p.id: p for p in chapter.locations}
    for loc in chapter.locations:
        loc.description = "SYNTHETIC CONTROL · invented story, not Qloo evidence. " + loc.description
    places["archive"].objects.append(
        WorldObject(
            id="control_note",
            name="Synthetic screening note",
            kind="object",
            x=20,
            y=10,
            text=f"Invented clue: {control.record} prints {control.motif} on its sleeve. No real cultural entity is represented.",
            choices=[
                Choice(
                    id="control_trace",
                    label=f"Record {control.record}'s sleeve motif (invented)",
                    requires=["map"],
                    grants=["control_trace"],
                    text="Recorded a synthetic story motif, not a Qloo relationship.",
                )
            ],
        )
    )
    places["quay"].objects.append(
        WorldObject(
            id="control_card",
            name="Synthetic film display",
            kind="object",
            x=20,
            y=10,
            text=f"Invented film: {control.film}. Its tram ticket repeats {control.motif}.",
            choices=[
                Choice(
                    id="control_memory",
                    label=f"Match {control.film}'s ticket motif (invented)",
                    requires=["rhythm", "control_trace"],
                    grants=["control_memory"],
                    text="The two invented props share a motif by author design, not measured affinity.",
                )
            ],
        )
    )
    for loc in chapter.locations:
        for obj in loc.objects:
            if obj.id == "mara":
                obj.text = "SYNTHETIC CONTROL · Mara points to a screening note in the boutique. Carry its sleeve motif to Ivo, then inspect the film display here."
            elif obj.id == "ivo":
                obj.text = "SYNTHETIC CONTROL · Ivo asks for the invented sleeve motif before teaching the rhythm. This is an authored puzzle, not a cultural inference."
                obj.choices[0].requires.append("control_trace")
            elif obj.id == "sera":
                obj.text = (
                    "SYNTHETIC CONTROL · Sera asks for the matching invented ticket before accepting a privacy promise."
                )
                for choice in obj.choices:
                    choice.requires.append("control_memory")
            elif obj.id == "beacon":
                obj.text = f"SYNTHETIC CONTROL · Match {control.record} and {control.film} through {control.motif}. Only the authored story supports this; no Qloo claim is possible."
                for choice in obj.choices:
                    if choice.ending:
                        choice.requires.append("control_proof")
                obj.choices.append(
                    Choice(
                        id="control_proof",
                        label=f"Present {control.record} and {control.film}: matching {control.motif} (authored motif proof)",
                        requires=["map", "rhythm", "chronicle", "control_trace", "control_memory"],
                        grants=["control_proof"],
                        text="The Curator accepts the authored motif solution. This proves no real-world cultural connection.",
                    )
                )
    return chapter
