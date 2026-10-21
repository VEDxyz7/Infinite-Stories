#!/usr/bin/env python3
"""Run only pinned Qloo help/no-key commands with network/process execution denied.

No dummy credential is created. A successful CLI startup is not API evidence.
"""

import argparse
import datetime
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", type=Path, required=True, help="Official package dist/bin.js")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    node = shutil.which("node")
    if not node or not args.cli.is_file():
        raise SystemExit("Node and a real installed CLI entry point are required")
    commands = [
        ["--version"],
        ["api", "search", "--help"],
        ["api", "insights", "--help"],
        ["exec", "--help"],
        ["api", "search", "--query", "Björk", "--type", "artist", "--take", "5", "--json", "--dry-run"],
        ["exec", "find_tags", "--input", '{"query":"jazz","limit":1}'],
    ]
    records = []
    with tempfile.TemporaryDirectory(prefix="infinite-stories-qloo-config-") as folder:
        env = {
            "PATH": os.path.dirname(node) + ":/usr/bin:/bin",
            "QLOO_HOME": folder,
            "PI_TELEMETRY": "0",
            "PI_SKIP_VERSION_CHECK": "1",
            "PI_OFFLINE": "1",
            "NO_COLOR": "1",
        }
        for command in commands:
            result = subprocess.run(
                [node, "--import", str(ROOT / "tools/deny-network.mjs"), str(args.cli.resolve()), *command],
                cwd=folder,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            records.append(
                {
                    "command": ["qloo", *command],
                    "exit_code": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
            )
            print(
                json.dumps(
                    {
                        "command": ["qloo", *command],
                        "exit_code": result.returncode,
                        "guard_zero_attempts": "OFFLINE_GUARD_ATTEMPTS=0" in result.stderr,
                    }
                )
            )
    payload = {
        "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "kind": "official_harness_offline_execution",
        "live_qloo_requests": 0,
        "records": records,
    }
    with args.output.open("x") as out:
        json.dump(payload, out, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
