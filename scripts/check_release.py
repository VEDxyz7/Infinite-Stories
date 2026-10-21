#!/usr/bin/env python3
"""Fail closed unless every independently evidenced release gate is PASS."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument(
        "--gates",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "reports/release_gates.json",
        help="Private local gate evidence; absence never implies release approval",
    )
    args = parser.parse_args()
    path = args.gates
    if not path.is_file():
        print("BLOCKED: local release gate evidence is absent; no release approval inferred.")
        return 0 if args.report_only else 2
    gates = json.loads(path.read_text())
    for name in "ABCDEFGH":
        gate = gates["gates"].get(name)
        if not gate or gate.get("status") not in ("PASS", "FAIL", "BLOCKED") or not gate.get("evidence"):
            raise SystemExit("Invalid or unevidenced release gate: " + name)
        print(name + ": " + gate["status"] + " — " + gate["summary"])
    ready = all(gates["gates"][g]["status"] == "PASS" for g in "ABCDEFGH")
    print("READY" if ready else "BLOCKED")
    return 0 if ready or args.report_only else 2


if __name__ == "__main__":
    raise SystemExit(main())
