#!/usr/bin/env python3
"""Offline by default. One fixed, approved OpenAI connectivity call; no gameplay claim."""

import argparse
import json
import os
import time
from pathlib import Path

import httpx

from scripts.qloo_smoke_test import load_env

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cost-approved", action="store_true", help="Only after the owner approves this estimate")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--output", type=Path, help="Optional new evidence file; never overwrites")
    args = parser.parse_args()
    plan = {
        "scope": "connectivity_only_not_game_master_acceptance",
        "provider": "openai",
        "model": "gpt-6-luna",
        "max_requests": 1,
        "automatic_retries": 0,
        "max_output_tokens": 64,
        "reasoning_effort": "none",
        "estimated_usd_upper_scenario": 0.0001,
    }
    if not args.live:
        print(json.dumps({**plan, "status": "NOT_TESTED", "provider_requests": 0}, indent=2))
        return 0
    if not args.cost_approved:
        print("BLOCKED: owner approval of this paid test is required; zero provider requests.")
        return 2
    if args.output and args.output.exists():
        print("BLOCKED: evidence output already exists; zero provider requests.")
        return 2
    try:
        private = load_env(args.env_file)
    except (OSError, ValueError):
        print("BLOCKED: private configuration could not be read; zero provider requests.")
        return 2
    # Preserve the backend's override precedence and ordinary process-over-file priority.
    config = {**private, **os.environ}
    key = config.get("IS_LLM_API_KEY") or config.get("OPENAI_API_KEY", "")
    if not key or key.startswith(("REPLACE_", "YOUR_")):
        print("BLOCKED: nonempty private OpenAI credential required; zero provider requests.")
        return 2
    started = time.monotonic()
    result = {**plan, "status": "FAIL", "provider_requests": 1}
    try:
        with httpx.Client(timeout=10, follow_redirects=False, trust_env=False) as client:
            with client.stream(
                "POST",
                "https://api.openai.com/v1/responses",
                headers={"Authorization": "Bearer " + key},
                json={
                    "model": plan["model"],
                    "store": False,
                    "max_output_tokens": 64,
                    "reasoning": {"effort": "none"},
                    "input": "Reply with exactly: ready",
                },
            ) as response:
                result["http_status"] = response.status_code
                if response.status_code == 200:
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 16384:
                            raise ValueError("Oversized response")
                    body = json.loads(raw)
                    text = "".join(
                        part.get("text", "")
                        for item in body.get("output", [])
                        if item.get("type") == "message"
                        for part in item.get("content", [])
                        if part.get("type") == "output_text"
                    )
                    if body.get("status") == "completed" and text.strip().casefold() == "ready":
                        result["status"] = "PASS_CONNECTIVITY_ONLY"
                    usage = body.get("usage", {})
                    result["usage"] = {
                        name: usage[name]
                        for name in ("input_tokens", "output_tokens", "total_tokens")
                        if isinstance(usage.get(name), int) and not isinstance(usage[name], bool)
                    }
                # Never print upstream error bodies, headers, identifiers, or generated text.
    except (httpx.HTTPError, ValueError, TypeError, AttributeError, KeyError):
        result["error"] = "TRANSPORT_OR_RESPONSE_INVALID"
    result["elapsed_ms"] = round((time.monotonic() - started) * 1000)
    encoded = json.dumps(result, indent=2) + "\n"
    if args.output:
        with args.output.open("x") as evidence:
            evidence.write(encoded)
    print(encoded, end="")
    return 0 if result["status"] == "PASS_CONNECTIVITY_ONLY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
