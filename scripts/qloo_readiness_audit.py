"""Read-only secret/evidence audit. No provider calls; print only counts and booleans."""

import json
import stat
from pathlib import Path

from scripts.qloo_smoke_test import load_env

ROOT = Path(__file__).resolve().parents[1]


def inspect():
    values = load_env(ROOT / ".env")
    needles = [values.get(name, "").encode() for name in ("QLOO_API_KEY", "OPENAI_API_KEY") if values.get(name)]
    excluded = {
        ".venv",
        ".git",
        "node_modules",
        "Library",
        "Temp",
        "Obj",
        "__pycache__",
        ".ruff_cache",
        ".pytest_cache",
    }
    paths = [
        p
        for base in ("backend", "scripts", "tests", "tools", "shared", "docs", "reports", "client")
        for p in (ROOT / base).rglob("*")
        if p.is_file() and not excluded.intersection(p.relative_to(ROOT).parts)
    ]
    paths += [p for p in ROOT.iterdir() if p.is_file() and p.name != ".env" and not p.name.startswith(".env.")]
    matches = web_count = log_count = 0
    for path in paths:
        found = False
        tail = b""
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                data = tail + chunk
                found = found or any(needle in data for needle in needles)
                tail = data[-max([len(n) for n in needles] or [1]) :]
        matches += found
        web_count += "Builds" in path.parts
        log_count += "Logs" in path.parts or path.suffix == ".log"
    records = []
    for folder, filenames in (
        ("qloo-two-request-20261020", ("resolve", "recommend")),
        ("qloo-cross-category-20261020", tuple(f"request-{i}" for i in range(1, 5))),
        ("qloo-remaining-categories-20261020", tuple(f"request-{i}" for i in range(1, 7))),
    ):
        records.extend(
            json.loads((ROOT / "reports/local" / folder / (name + ".json")).read_text()) for name in filenames
        )
    feasibility_attempts = sum(x["fetch_attempts"] for x in records)
    production = ROOT / "reports/QLOO_PRODUCTION_ADAPTER_LIVE_20261020.json"
    production_records = json.loads(production.read_text()).get("operations", []) if production.is_file() else []
    return {
        "kind": "offline_readiness_audit",
        "initial_feasibility_attempts": feasibility_attempts,
        "production_adapter_live_attempts": len(production_records),
        "new_live_qloo_requests": 0,
        "new_openai_requests": 0,
        "historical_qloo_attempts": feasibility_attempts + len(production_records),
        "historical_statuses": [x["http_status"] for x in records] + [x["http_status"] for x in production_records],
        "configured_secret_count": len(needles),
        "scanned_files": len(paths),
        "web_build_files_scanned": web_count,
        "project_log_files_scanned": log_count,
        "files_containing_configured_secret_values": matches,
        "env_mode": oct(stat.S_IMODE((ROOT / ".env").stat().st_mode)),
        "scope": "exact configured-key value scan of project source, reports/private projections, existing uncompressed Web artifact and project logs; not proof for external/historical systems",
    }


if __name__ == "__main__":
    print(json.dumps(inspect(), indent=2))
