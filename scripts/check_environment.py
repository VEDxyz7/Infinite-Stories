#!/usr/bin/env python3
"""Read-only local prerequisites. Never prints secret values or contacts providers."""

import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EDITOR = Path("/Applications/Unity/Hub/Editor/6000.3.26f1/Unity.app/Contents/MacOS/Unity")


def inspect():
    editor = Path(os.environ.get("UNITY_EDITOR", str(DEFAULT_EDITOR))).expanduser()
    # Hub installs optional modules beside Unity.app; built-in modules can be inside it.
    modules = []
    if editor.name == "Unity" and len(editor.parents) >= 4:
        for root in (editor.parents[3] / "PlaybackEngines", editor.parents[1] / "PlaybackEngines"):
            if root.is_dir():
                modules.extend(str(p) for p in root.iterdir() if p.name == "WebGLSupport")
    dotenv = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                dotenv[key.strip()] = value.strip().strip("\"'")
    return {
        "unity_editor": str(editor),
        "unity_executable_accessible": editor.is_file() and os.access(editor, os.X_OK),
        "web_module_locations": sorted(set(modules)),
        "unity_activation": "Requires actual batch launch; file presence alone is not proof.",
        "tools": {name: shutil.which(name) for name in ("node", "npm", "vercel", "docker", "psql", "gh")},
        "postgres_binary": str(Path("/opt/homebrew/opt/postgresql@17/bin/postgres"))
        if Path("/opt/homebrew/opt/postgresql@17/bin/postgres").is_file()
        else shutil.which("postgres"),
        "credentials_present": {
            name: bool(os.environ.get(name) or dotenv.get(name))
            for name in ("QLOO_API_KEY", "IS_LLM_API_KEY", "OPENAI_API_KEY", "VERCEL_TOKEN")
        },
        "approved_qloo_origin": "https://hackathon.api.qloo.com",
        "network_requests": 0,
    }


if __name__ == "__main__":
    print(json.dumps(inspect(), indent=2))
