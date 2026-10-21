"""Offline feasibility proof over private actual Qloo evidence; never calls a provider.

Creates an isolated overlay on the authored map. Does not enable cultural sessions,
change production source attribution, or persist anything in the gameplay database.
"""

import copy
import hashlib
import json
from uuid import UUID

from backend.app.content import make_chapter, validate_chapter
from backend.app.engine import apply_command
from backend.app.models import Choice, Command, DomainError, GameState, WorldObject
from scripts.qloo_gate_request import HOST, LOCAL, valid
from scripts.qloo_smoke_test import normalize


def build_decision(search, recommendations):
    for record, path in ((search, "/search"), (recommendations, "/v2/insights")):
        if (
            record.get("http_status") != 200
            or record.get("cli_exit_code") != 0
            or record.get("origin") != HOST
            or record.get("path") != path
            or not record.get("body_sha256")
            or not record.get("at_utc")
        ):
            raise ValueError("Missing successful live request provenance")
    seeds = [
        e
        for e in search["entities"]
        if valid(e, "artist", search) and normalize(e["name"]) == normalize("Björk")
    ]
    if len(seeds) != 1:
        raise ValueError("Ambiguous or missing seed")
    seed = seeds[0]
    if recommendations["params"].get("signal.interests.entities") != seed["entity_id"]:
        raise ValueError("Recommendation signal differs from confirmed seed")
    if recommendations["params"].get("filter.type") != "urn:entity:movie":
        raise ValueError("Wrong target category")
    movies = []
    seen = set()
    for entity in recommendations["entities"]:
        if (
            valid(entity, "movie")
            and entity["entity_id"].lower() not in seen
            and entity["entity_id"].lower() != seed["entity_id"].lower()
        ):
            movies.append(entity)
            seen.add(entity["entity_id"].lower())
    if not movies:
        raise ValueError("No valid actual recommendation")
    target = movies[0]  # Response order, not a fabricated affinity score.
    tags = {t.get("id") for t in target.get("tags", [])}
    stage = (
        "paper_theater"
        if "urn:tag:theme:qloo:art_and_creativity" in tags
        else "archive_screen"
    )
    tag = "urn:tag:theme:qloo:art_and_creativity" if stage == "paper_theater" else None
    answer = "echo_" + str(UUID(target["entity_id"]))
    chapter = make_chapter().model_copy(deep=True)
    archive = next(loc for loc in chapter.locations if loc.id == "archive")
    archive.objects.append(
        WorldObject(
            id="cultural_echo",
            name="Paper theater" if stage == "paper_theater" else "Archive screen",
            kind="object",
            x=18,
            y=6,
            text=f"Qloo returned {target['name']} among film recommendations for {seed['name']}. Carry this film's card to Sera.",
            choices=[
                Choice(
                    id=answer,
                    label="Carry the card: " + target["name"],
                    requires=["rhythm"],
                    grants=["culture_echo"],
                    text="You carry the chosen film card to the keeper.",
                )
            ],
        )
    )
    sera = next(obj for obj in archive.objects if obj.id == "sera")
    for choice in sera.choices:
        choice.requires.append("culture_echo")
    validate_chapter(chapter)
    decision = {
        "context_source": "live_qloo",
        "rule": "response-order-film-card-v1",
        "seed_id": seed["entity_id"],
        "target_id": target["entity_id"],
        "target_name": target["name"],
        "quest_slot": "archive/cultural_echo",
        "answer_choice_id": answer,
        "stage": stage,
        "supporting_tag_id": tag,
        "evidence_fields": [
            "entity_id",
            "name",
            "subtype",
            "tags.id",
            "tags.name",
            "tags.type",
        ],
        "source_requests": [
            {
                "path": x["path"],
                "params": x["params"],
                "at_utc": x["at_utc"],
                "body_sha256": x["body_sha256"],
            }
            for x in (search, recommendations)
        ],
        "creative_content_source": "local_authored_rule_no_llm",
        "creative_interpretation": "Film membership selects the required quest card; art/creativity tag selects original paper-theater presentation.",
        "scope": "isolated feasibility overlay on original authored map; not production cultural session",
    }
    return chapter, decision


def rejected(fn, expected=None):
    try:
        fn()
    except (ValueError, DomainError) as error:
        if expected and getattr(error, "code", None) != expected:
            raise AssertionError("Unexpected rejection category") from error
        return True
    raise AssertionError("Invalid case accepted")


def main():
    search = json.loads((LOCAL / "resolve.json").read_text())
    recs = json.loads((LOCAL / "recommend.json").read_text())
    assert search["fetch_attempts"] + recs["fetch_attempts"] == 2
    chapter, decision = build_decision(search, recs)
    checks = {}
    original_hash = hashlib.sha256(
        make_chapter().model_dump_json().encode()
    ).hexdigest()
    state = GameState()

    def command(**kwargs):
        nonlocal state
        state, _ = apply_command(chapter, state, Command(**kwargs))

    def move(x, y):
        for axis, destination in (("y", 8), ("x", x), ("y", y)):
            while abs(getattr(state, axis) - destination) > 0.01:
                point = {"x": state.x, "y": state.y}
                point[axis] += max(-3, min(3, destination - point[axis]))
                command(kind="position", **point)

    def choose(target, choice, x=14, y=9):
        move(x, y)
        command(kind="choose", target=target, choice=choice)

    def travel():
        move(29, 8)
        command(kind="travel", target=state.location_id + "_east")

    choose("mara", "take_map")
    travel()
    choose("ivo", "learn_rhythm")
    travel()
    move(14, 9)
    checks["quest_cannot_progress_without_cultural_card"] = rejected(
        lambda: apply_command(
            chapter,
            state,
            Command(kind="choose", target="sera", choice="promise_guard"),
        ),
        "PREREQUISITE_MISSING",
    )
    move(18, 6)
    checks["unreturned_answer_rejected"] = rejected(
        lambda: apply_command(
            chapter,
            state,
            Command(
                kind="choose",
                target="cultural_echo",
                choice="echo_00000000-0000-4000-8000-000000000000",
            ),
        ),
        "PREREQUISITE_MISSING",
    )
    command(kind="choose", target="cultural_echo", choice=decision["answer_choice_id"])
    checks["actual_recommendation_changes_required_game_state"] = (
        "culture_echo" in state.flags
    )
    choose("sera", "promise_guard")
    travel()
    choose("beacon", "light_together")
    checks["actual_engine_route_completes_within_12_visits"] = (
        state.ending == "together" and state.visits == 4
    )
    checks["source_authored_chapter_unchanged"] = (
        hashlib.sha256(make_chapter().model_dump_json().encode()).hexdigest()
        == original_hash
    )
    absent = copy.deepcopy(recs)
    absent["entities"] = []
    checks["empty_actual_context_blocks_generation"] = rejected(
        lambda: build_decision(search, absent)
    )
    mismatch = copy.deepcopy(recs)
    mismatch["params"]["signal.interests.entities"] = (
        "00000000-0000-4000-8000-000000000000"
    )
    checks["mismatched_query_provenance_rejected"] = rejected(
        lambda: build_decision(search, mismatch)
    )
    removed = copy.deepcopy(recs)
    removed["entities"] = [
        e for e in recs["entities"] if e["entity_id"] != decision["target_id"]
    ]
    _, alternate = build_decision(search, removed)
    checks["removing_selected_result_changes_quest_answer"] = (
        alternate["answer_choice_id"] != decision["answer_choice_id"]
    )
    assert all(checks.values()), checks
    proof = {
        "status": "PASS",
        "scope": "backend feasibility decision only",
        "live_requests": 2,
        "additional_provider_requests": 0,
        "checks": checks,
        "decision": decision,
        "final_state": {
            "ending": state.ending,
            "visits": state.visits,
            "flags": state.flags,
        },
        "base_map_source": "authored_original",
        "overlay_context_source": "live_qloo",
    }
    out = LOCAL / "decision-proof.json"
    with out.open("x") as file:
        json.dump(proof, file, indent=2, ensure_ascii=False)
    out.chmod(0o600)
    print(
        json.dumps(
            {
                "status": proof["status"],
                "checks": checks,
                "selected_movie": decision["target_name"],
                "stage": decision["stage"],
                "ending": state.ending,
                "visits": state.visits,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
