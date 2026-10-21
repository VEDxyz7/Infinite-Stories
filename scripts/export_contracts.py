#!/usr/bin/env python3
"""Export implemented schemas, or fail if checked-in contracts have drifted."""

import argparse
import json
from pathlib import Path

from backend.app.main import create_app
from backend.app.models import ActionRequest, Chapter, GameState, GameView, TurnRequest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    folder = Path(__file__).resolve().parents[1] / "shared/schemas"
    folder.mkdir(parents=True, exist_ok=True)
    data = {
        name + ".schema.json": model.model_json_schema()
        for name, model in [
            ("chapter", Chapter),
            ("game_state", GameState),
            ("game_view", GameView),
            ("action_request", ActionRequest),
            ("turn_request", TurnRequest),
        ]
    }
    data["openapi.json"] = create_app().openapi()
    for name, body in data.items():
        path = folder / name
        if args.check:
            if not path.exists() or json.loads(path.read_text()) != body:
                raise SystemExit("Contract drift: " + name)
        else:
            path.write_text(json.dumps(body, indent=2) + "\n")
    print("Implemented API/data schemas match source" if args.check else "Exported implemented API/data schemas")


if __name__ == "__main__":
    main()
