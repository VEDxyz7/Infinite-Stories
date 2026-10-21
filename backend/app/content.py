"""Original authored chapter. No cultural entities or simulated provider data."""

from collections import deque

from .models import Chapter, Choice, DomainError, GameState, Location, WorldObject


def make_chapter() -> Chapter:
    places = [
        (
            "quay",
            "Lantern Quay",
            "Salt air, copper lamps, and a city waiting for dawn.",
            WorldObject(
                id="mara",
                name="Mara · record keeper",
                kind="npc",
                x=14,
                y=9,
                text="The station needs three memories: a way home, a rhythm, and a promise. I can give you the first.",
                choices=[
                    Choice(
                        id="take_map",
                        label="Accept Mara's hand-drawn map",
                        grants=["map"],
                        text="Mara folds a map into your palm. The first memory is a way home.",
                    )
                ],
            ),
            WorldObject(
                id="harbor_bell",
                name="Harbor bell",
                kind="object",
                x=20,
                y=6,
                text="A ship's bell rings twice. Beyond the eastern arch, the Night Market is still awake.",
            ),
        ),
        (
            "market",
            "Night Market",
            "Shutters half closed. A quiet rhythm carries through the rain.",
            WorldObject(
                id="ivo",
                name="Ivo · projectionist",
                kind="npc",
                x=14,
                y=9,
                text="A city remembers through the people who keep its rhythm. Show me that you know the way home.",
                choices=[
                    Choice(
                        id="learn_rhythm",
                        label="Trade the map's story for Ivo's rhythm",
                        requires=["map"],
                        grants=["rhythm"],
                        text="Ivo taps the projector housing in time with its shutter. You carry the second memory onward.",
                    )
                ],
            ),
            WorldObject(
                id="lantern",
                name="Broken lantern",
                kind="object",
                x=20,
                y=6,
                text="Its glass is cracked, but the wick is sound.",
                choices=[
                    Choice(
                        id="mend_lantern",
                        label="Relight the market lantern",
                        grants=["kindness"],
                        text="Warm light spills across the cinema entrance. Someone will remember your kindness.",
                    )
                ],
            ),
        ),
        (
            "archive",
            "House of Echoes",
            "Paper stars hang above shelves of stories never sent.",
            WorldObject(
                id="sera",
                name="Sera · collector & tailor",
                kind="npc",
                x=14,
                y=9,
                text="One last promise will open the station. A memory should be chosen, not taken.",
                choices=[
                    Choice(
                        id="promise_share",
                        label="Promise to share the city's stories",
                        requires=["rhythm"],
                        grants=["chronicle", "sharing"],
                        text="Sera gives you the chronicle. You promise that these voices will travel.",
                    ),
                    Choice(
                        id="promise_guard",
                        label="Promise to protect the private letters",
                        requires=["rhythm"],
                        grants=["chronicle", "guarding"],
                        text="Sera seals the chronicle. You promise that some memories will remain private.",
                    ),
                ],
            ),
            WorldObject(
                id="letters",
                name="Unsent letters",
                kind="object",
                x=20,
                y=6,
                text="The letters belong to the people who wrote them. Their silence is part of the story.",
            ),
        ),
        (
            "station",
            "Dawn Station",
            "The tram waits beneath an unlit beacon. Three empty sockets catch the moonlight.",
            WorldObject(
                id="beacon",
                name="The Curator",
                kind="gate",
                x=14,
                y=9,
                text="A way home, a rhythm, a promise. Together they can wake the dawn tram.",
                choices=[
                    Choice(
                        id="light_together",
                        label="Light the beacon and leave together",
                        requires=["map", "rhythm", "chronicle"],
                        grants=["beacon"],
                        ending="together",
                        text="The beacon wakes. Mara, Ivo and Sera board with you. The city becomes a story carried by many voices.",
                    ),
                    Choice(
                        id="leave_keeper",
                        label="Open the gate, then stay as its keeper",
                        requires=["map", "rhythm", "chronicle"],
                        grants=["beacon"],
                        ending="keeper",
                        text="The tram carries your friends toward dawn. You stay to keep the lamps burning for the next traveler.",
                    ),
                ],
            ),
            WorldObject(
                id="tram",
                name="The dawn tram",
                kind="object",
                x=20,
                y=6,
                text="The tram cannot leave until the last beacon is lit.",
            ),
        ),
    ]
    locations = []
    for i, (lid, name, description, npc, obj) in enumerate(places):
        # 0 = walkable paving; 1 = solid stone; 2 = water. Same collision data
        # drives server validation and the Unity Tilemap. Coordinates use rows[y].
        rows = []
        for y in range(18):
            row = []
            for x in range(32):
                solid = x in (0, 31) or y in (0, 17) or (7 <= x <= 10 and 11 <= y <= 14)
                row.append("1" if solid else "0")
            rows.append("".join(row))
        objects = [
            npc,
            obj,
            WorldObject(
                id=lid + "_east",
                name="East arch",
                kind="portal",
                x=29,
                y=8,
                text="Continue through the eastern arch.",
                destination=places[(i + 1) % 4][0],
            ),
            WorldObject(
                id=lid + "_west",
                name="West arch",
                kind="portal",
                x=2,
                y=8,
                text="Return through the western arch.",
                destination=places[(i - 1) % 4][0],
            ),
        ]
        locations.append(
            Location(id=lid, name=name, description=description, width=32, height=18, rows=rows, objects=objects)
        )
    chapter = Chapter(
        schema_version=1,
        id="last_light",
        version=1,
        title="The Last Light",
        source="authored_original",
        locations=locations,
    )
    validate_chapter(chapter)
    return chapter


def walkable(location: Location, x: float, y: float) -> bool:
    # Match the Unity traveler's circle against solid cell AABBs.
    import math

    radius = 0.28
    if (
        not radius + 0.5 <= x <= location.width - 1.5 - radius
        or not radius + 0.5 <= y <= location.height - 1.5 - radius
    ):
        return False
    for iy in range(math.floor(y - radius + 0.5), math.floor(y + radius + 0.5) + 1):
        for ix in range(math.floor(x - radius + 0.5), math.floor(x + radius + 0.5) + 1):
            if location.rows[iy][ix] != "0":
                dx, dy = max(abs(x - ix) - 0.5, 0), max(abs(y - iy) - 0.5, 0)
                if dx * dx + dy * dy < radius * radius - 1e-8:
                    return False
    return True


def validate_chapter(chapter: Chapter):
    ids = [loc.id for loc in chapter.locations]
    if len(set(ids)) != 4 or len(ids) != 4:
        raise ValueError("Chapter needs four unique locations")
    objects, choices = set(), set()
    graph = {}
    for loc in chapter.locations:
        if len(loc.rows) != loc.height or any(len(row) != loc.width or set(row) - set("012") for row in loc.rows):
            raise ValueError("Invalid tile data")
        if not walkable(loc, 4, 5) or not walkable(loc, 3, 8) or not walkable(loc, 28, 8):
            raise ValueError("Blocked spawn")
        graph[loc.id] = []
        reachable = {(4, 5)}
        queue = deque(reachable)
        while queue:
            x, y = queue.popleft()
            for point in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if point not in reachable and walkable(loc, *point):
                    reachable.add(point)
                    queue.append(point)
        for obj in loc.objects:
            if obj.id in objects or (int(obj.x), int(obj.y)) not in reachable:
                raise ValueError("Duplicate or unreachable object")
            objects.add(obj.id)
            if obj.kind == "portal":
                if obj.destination not in ids:
                    raise ValueError("Unknown portal destination")
                graph[loc.id].append(obj.destination)
            for choice in obj.choices:
                if choice.id in choices:
                    raise ValueError("Duplicate choice")
                choices.add(choice.id)
    visited, pending = set(), [ids[0]]
    while pending:
        lid = pending.pop()
        if lid not in visited:
            visited.add(lid)
            pending.extend(graph[lid])
    if len(visited) != 4:
        raise ValueError("Disconnected chapter")


def current_location(chapter: Chapter, state: GameState) -> Location:
    loc = next((loc for loc in chapter.locations if loc.id == state.location_id), None)
    if not loc or not walkable(loc, state.x, state.y):
        raise DomainError("SAVE_INVALID", "This save cannot be safely resumed.", 503)
    return loc
