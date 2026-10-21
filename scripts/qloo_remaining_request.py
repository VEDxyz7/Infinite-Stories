#!/usr/bin/env python3
"""Six-request remaining-category gate via the existing official CLI. Each operation is permanently reserved before launch.

No retries; no model calls. Evidence is private and minimal. Re-running an operation
is refused, including after failure. Does not enable production cultural generation.
"""

import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from uuid import UUID

from scripts.qloo_smoke_test import load_env, normalize, redact

ROOT = Path(__file__).resolve().parents[1]
HOST = "https://hackathon.api.qloo.com"
LOCAL = ROOT / "reports/local/qloo-remaining-categories-20261020"
REQUESTS = {
    1: ("Dune", "book", None),
    2: ("Dune", "book", "movie"),
    3: ("LEGO", "brand", None),
    4: ("LEGO", "brand", "movie"),
    5: ("The Legend of Zelda: Breath of the Wild", "videogame", None),
    6: ("The Legend of Zelda: Breath of the Wild", "videogame", "movie"),
}


def valid(entity, category, request=None):
    try:
        UUID(entity["entity_id"])
        expected = "urn:entity:" + category
        category_match = (
            entity.get("subtype") or entity.get("type")
        ) == expected or expected in entity.get("types", [])
        return bool(entity.get("name")) and bool(category_match)
    except (KeyError, TypeError, ValueError):
        return False


def seed_candidates(record, name, category):
    candidates = [e for e in record.get("entities", []) if valid(e, category)]
    if category == "book":
        # Actual returned canonical title; match the specifically requested novel,
        # not other Dune works that mention Frank Herbert in a description.
        return [
            e
            for e in candidates
            if normalize(e.get("name", ""))
            in (normalize(name), normalize("Dune (Dune, #1)"))
            and normalize(e.get("disambiguation", ""))
            == normalize("1965, Frank Herbert")
            and e.get("properties", {}).get("publication_year") == 1965
        ]
    if category == "brand":
        return [
            e
            for e in candidates
            if normalize(e.get("name", "")) in (normalize(name), "the lego group")
            and "lego"
            in normalize(e.get("properties", {}).get("short_description", ""))
            and "construction"
            in normalize(e.get("properties", {}).get("short_description", ""))
        ]
    return [e for e in candidates if normalize(e.get("name", "")) == normalize(name)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request_number", type=int, choices=[1, 2, 3, 4, 5, 6])
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--user-authorized", action="store_true", required=True)
    parser.add_argument("--confirmed-id")
    args = parser.parse_args()
    values = {**load_env(ROOT / ".env"), **os.environ}
    if not values.get("QLOO_API_KEY"):
        raise SystemExit("Required configured variables are missing; values suppressed")
    node = shutil.which("node")
    if not node or not args.cli.is_file():
        raise SystemExit("Existing official CLI and Node required")
    LOCAL.mkdir(parents=True, exist_ok=True, mode=0o700)
    LOCAL.chmod(0o700)
    name, source_category, target_category = REQUESTS[args.request_number]
    operation = f"request-{args.request_number}"
    if target_category is None:
        path = "/search"
        command = [
            "api",
            "--verbose",
            "search",
            "--query",
            name,
            "--type",
            source_category,
            "--take",
            "5",
            "--json",
        ]
        category = source_category
    else:
        previous = json.loads(
            (LOCAL / f"request-{args.request_number - 1}.json").read_text()
        )
        matches = seed_candidates(previous, name, source_category)
        if (
            previous.get("http_status") != 200
            or previous.get("cli_exit_code") != 0
            or len(matches) != 1
            or matches[0]["entity_id"] != args.confirmed_id
        ):
            raise SystemExit(
                "No unique verified and explicitly confirmed seed; dependent request refused"
            )
        path = "/v2/insights"
        command = [
            "api",
            "--verbose",
            "insights",
            "--type",
            target_category,
            "--signal-entities",
            args.confirmed_id,
            "--take",
            "5",
            "--json",
        ]
        category = target_category
    # Exclusive reservations prevent repeats even if a prior request crashed.
    reservation = LOCAL / (operation + ".reserved")
    with reservation.open("x") as f:
        f.write("user_authorized_working_assumptions_not_organizer_verified\n")
    reservation.chmod(0o600)
    target = LOCAL / (operation + ".json")
    config = LOCAL / "config"
    config.mkdir(exist_ok=True, mode=0o700)
    env = {
        "PATH": os.path.dirname(node) + ":/usr/bin:/bin",
        "QLOO_HOME": str(config),
        "QLOO_API_KEY": values["QLOO_API_KEY"],
        "QLOO_BASE_URL": HOST,
        "QLOO_TRUSTED_BASE_URL": HOST,
        "IS_QLOO_EVIDENCE": str(target),
        "IS_QLOO_PATH": path,
        "PI_TELEMETRY": "0",
        "PI_SKIP_VERSION_CHECK": "1",
        "NO_COLOR": "1",
    }
    start = time.monotonic()
    try:
        result = subprocess.run(
            [
                node,
                "--import",
                str(ROOT / "tools/qloo/remaining-bounded-fetch.mjs"),
                str(args.cli.resolve()),
                *command,
            ],
            env=env,
            cwd=config,
            capture_output=True,
            text=True,
            timeout=30,
        )
        code = result.returncode
        # stdout/stderr never persisted or echoed: may include upstream arbitrary errors.
    except subprocess.TimeoutExpired:
        code = None
    evidence = (
        json.loads(target.read_text())
        if target.exists()
        else {"fetch_attempts": 0, "outcome": "CLI_FAILED_BEFORE_FETCH", "entities": []}
    )
    evidence.update(
        operation=operation,
        request_number=args.request_number,
        source_category=source_category,
        target_category=target_category,
        cli_exit_code=code,
        command_elapsed_ms=round((time.monotonic() - start) * 1000),
        harness_version="0.1.26",
        authorization_source="user_approved_working_assumptions",
        organizer_verified=False,
    )
    seen = set()
    normalized = []
    for e in evidence.get("entities", []):
        if (
            valid(e, category, evidence)
            and e["entity_id"].lower() not in seen
            and e["entity_id"] != args.confirmed_id
        ):
            normalized.append(e)
            seen.add(e["entity_id"].lower())
    evidence["valid_distinct_result_count"] = len(normalized)
    evidence["rejected_or_duplicate_count"] = len(evidence.get("entities", [])) - len(
        normalized
    )
    evidence = redact(
        evidence, [values.get("QLOO_API_KEY"), values.get("OPENAI_API_KEY")]
    )
    target.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n")
    target.chmod(0o600)
    summary = {k: v for k, v in evidence.items() if k != "entities"}
    summary["entity_previews"] = [
        {
            **{
                k: e[k]
                for k in (
                    "entity_id",
                    "name",
                    "type",
                    "subtype",
                    "types",
                    "disambiguation",
                    "tag_count",
                    "query_fields",
                )
                if k in e
            },
            "properties": {
                k: (v[:300] if isinstance(v, str) else v)
                for k, v in e.get("properties", {}).items()
            },
            "tags": e.get("tags", [])[:5],
            "observed_fields": e.get("observed_fields", []),
        }
        for e in evidence.get("entities", [])
    ]
    if target_category is None:
        summary["verified_seed_matches"] = len(
            seed_candidates(evidence, name, source_category)
        )
        summary["exact_name_matches"] = sum(
            normalize(e.get("name", "")) == normalize(name)
            for e in evidence.get("entities", [])
        )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
