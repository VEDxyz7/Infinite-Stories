"""Small abstract model for Phase 0 only. No Unity/game/backend implementation.

Input evidence must be independently verified by a future Qloo ingestion adapter.
This model proves route constraints, not the truth or provenance of that evidence.
"""
from collections import deque


def validate(city, evidence):
    def reject(reason):
        return {"status": "REJECT", "reason": reason}

    locations = city["locations"]
    clues = city["clues"]
    if len(locations) != 4 or len(set(locations)) != 4:
        return reject("Exactly four distinct locations required")
    residents = city["residents"]
    if len(residents) != 3 or len(set(residents)) != 3 or any(loc not in locations for loc in residents.values()):
        return reject("Exactly three residents with valid locations required")
    if city["gate_location"] not in locations or not 1 <= city["budget"] <= 12:
        return reject("Invalid gate or visit budget")
    for clue in clues.values():
        if clue["location"] not in locations:
            return reject("Unknown clue location")
        if not clue["evidence"] or any(e not in evidence for e in clue["evidence"]):
            return reject("Missing stored clue evidence")
        if any(c not in clues for c in clue["requires"]):
            return reject("Unknown dependency")
    answers = city["answers"]
    if not answers:
        return reject("No accepted answer")
    for answer in answers:
        if not answer["requires"] or any(c not in clues for c in answer["requires"]):
            return reject("Answer dependencies missing")
        edge = evidence.get(answer["evidence"])
        if not edge or edge.get("kind") != "recommendation" or not edge.get("source_id") or not edge.get("target_id"):
            return reject("Missing answer evidence")
        if not edge.get("source_type") or not edge.get("target_type") or edge["source_type"] == edge["target_type"]:
            return reject("Answer must cross categories")
        disclosed = set().union(*(set(clues[c]["evidence"]) for c in answer["requires"]))
        if answer["evidence"] not in disclosed:
            return reject("Answer evidence is hidden from its required clues")
    # State = location, discovered-clue set, visited-location set. All moves cost
    # one visit, including first entry, revisits, and gate entry. Actions inside
    # a location cost zero in this explicitly chosen abstract visit model.
    queue = deque([(None, frozenset(), frozenset(), [])])
    seen = {(None, frozenset(), frozenset())}
    while queue:
        current, found, visited, route = queue.popleft()
        if current == city["gate_location"] and len(visited) == 4:
            for i, answer in enumerate(answers):
                if set(answer["requires"]) <= found and len(found) == len(clues):
                    return {"status": "VALID_ABSTRACT", "visits": len(route), "route": route, "answer_index": i}
        if len(route) >= city["budget"]:
            continue
        for location in sorted(locations):
            if location == current:
                continue
            next_found = set(found)
            while True:
                before = len(next_found)
                for cid, clue in clues.items():
                    if clue["location"] == location and set(clue["requires"]) <= next_found:
                        next_found.add(cid)
                if len(next_found) == before:
                    break
            state = (location, frozenset(next_found), visited | {location})
            if state not in seen:
                seen.add(state)
                queue.append((*state, route + [location]))
    return reject("No winning route within budget")
