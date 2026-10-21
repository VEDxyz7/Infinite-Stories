# Infinite Stories

A top-down Unity night-city RPG with four connected areas, three residents,
a twelve-visit clock, consequential choices and persistent saves. Investigate
cultural connections through a server-side Qloo adapter, or play the explicitly
authored chapter without providers. An optional local LLM interprets free-form
actions; the backend validates every proposed action before changing game state.

Supported cultural paths are **artists → films, films → artists, brands → films,
and video games → films**. Books and arbitrary category combinations are not
supported. Qloo evidence and fictional story interpretation are kept separate;
aggregate affinities are not individual personality facts.

This is a work in progress, not a production-ready public service. Venue interiors,
story presentation, audio and broader browser/deployment acceptance need further
work. Local inference requires an accessible machine running the model; it is not
free public hosting. Historical test reports and private provider captures are
intentionally excluded from this repository.

New cultural runs follow a complete evidence chain: Mara's map → Ivo's screening
notes → Sera's memory cards and privacy promise → a supported affinity claim to
the Curator → an ending and Taste Card. Only entering a district spends a visit;
looking, talking and rejected claims are free. Older saves retain their original
rules. The Scanner searches this run's saved catalogue, shows related results and
provenance, tracks progress and records nearby validated discoveries; it does not
silently perform live searches. See [the gameplay specification](docs/GAMEPLAY_SPEC.md).

## Backend

Use Python3.12. From the repository root:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip==26.2.1
.venv/bin/python -m pip install -r backend/requirements-dev.txt
.venv/bin/python -m uvicorn backend.app.main:create_app --factory --host 127.0.0.1 --port 8042 --no-access-log
```

API documentation: http://127.0.0.1:8042/docs . `/healthz` checks liveness;
`/readyz` checks configured readiness. Start an **authored chapter** to play without
provider access. Cultural generation and model calls are disabled by default.

The backend reads process environment variables, **not `.env` automatically**.
[.env.example](.env.example) contains placeholders and available settings; keep
real credentials private. SQLite saves default to `data/infinite_stories.sqlite3`.
Production configuration requires PostgreSQL and exact HTTPS client origins.
[compose.yaml](compose.yaml) provides an optional PostgreSQL/backend configuration;
it requires private database settings and is not a deployed service.

## Unity and browser build

Open `client/` with **Unity6000.3.26f1**, including Web Build Support. Open
`Assets/InfiniteStories/Scenes/Chapter.unity` and press Play with the backend
running. **Infinite Stories → Prepare chapter scene** creates missing scene,
prefab and settings assets without replacing existing ones. Configure only the
public backend origin in `ClientSettings`; never put provider keys in Unity.

For batch commands, set `UNITY_EDITOR` to your installed Unity executable:

```sh
IS_PUBLIC_API_URL=http://127.0.0.1:8042 "$UNITY_EDITOR" -batchmode -quit -projectPath "$PWD/client" -executeMethod InfiniteStories.Editor.ProjectBuilder.BuildDevelopmentWeb -logFile /tmp/infinite-stories-build.log
python3 -m http.server 8080 --bind 127.0.0.1 --directory client/Builds/WebDevelopment
```

Open http://127.0.0.1:8080 . WASD/arrows move, E interacts, C opens the Scanner, J opens the Journal,
and Esc closes a panel or opens the menu.
Accessible HTML controls use the same Unity controller. Scanner and Journal show
confirmed cultural evidence and progress; the Qloo-off comparison is labelled
invented authored control and never changes saved context. Resume uses this
browser's private guest token; clearing browser storage loses guest recovery.

For a release artifact, use `ProjectBuilder.BuildWeb` with
`IS_PUBLIC_API_URL=https://YOUR_BACKEND_ORIGIN`. Build output is ignored; build it
locally rather than committing it. A successful build is not deployment approval.

## Optional local Game Master

Install [Ollama](https://ollama.com/) separately and explicitly download the local
`qwen3.5:4b` model (`ollama pull qwen3.5:4b`). Runtime and weights are not bundled.
Keep the listener private and disable cloud inference:

```sh
OLLAMA_NO_CLOUD=1 OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_MAX_QUEUE=4 ollama serve
```

Then start the backend with local inference enabled:

```sh
IS_LLM_PROVIDER=ollama IS_LLM_MODEL=qwen3.5:4b IS_LLM_CALLS_ALLOWED=true \
.venv/bin/python -m uvicorn backend.app.main:create_app --factory --host 127.0.0.1 --port 8042 --no-access-log
```

Stop an existing backend on that port before starting its replacement. No model
key is required. The adapter uses the fixed loopback origin, bounded requests,
typed tool proposals and authoritative engine validation, with no paid fallback.
Model unavailability preserves confirmed progress and surfaces a retry/recovery
error. Model quality and concurrency must be evaluated on the actual host.

Live Qloo generation additionally needs a private `QLOO_API_KEY` and explicit
`IS_QLOO_CALLS_ALLOWED=true`, using `https://hackathon.api.qloo.com`. Do not enable
it without the account owner's authorization and confirmed allocation/terms.
The optional OpenAI adapter likewise needs explicit provider/model/key/call
configuration and spending approval; it is not enabled by local Ollama setup.

## Tests and tooling

```sh
.venv/bin/python -m pytest tests/test_phase0.py -q
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python -m scripts.export_contracts --check
.venv/bin/python scripts/check_release.py --report-only
"$UNITY_EDITOR" -batchmode -nographics -projectPath "$PWD/client" -runTests -testPlatform EditMode -testResults /tmp/infinite-stories-edit.xml -logFile /tmp/infinite-stories-edit.log
"$UNITY_EDITOR" -batchmode -nographics -projectPath "$PWD/client" -runTests -testPlatform PlayMode -testResults /tmp/infinite-stories-play.xml -logFile /tmp/infinite-stories-play.log
```

Ordinary tests use synthetic/controlled HTTP responses, not live providers.
Real PostgreSQL tests require a **disposable** `IS_TEST_POSTGRES_URL`; alternatively
run `.venv/bin/python -m scripts.verify_postgres --output /tmp/NEW_EVIDENCE.json`
with PostgreSQL17 binaries installed. Unity HTTP tests require a running backend
and `IS_UNITY_HTTP_TESTS=1`; set `IS_UNITY_TEST_API_URL` if needed. The
free-form input focus check requires a backend advertising a configured Game
Master; the client deliberately disables that input when the model is unavailable.
The HTTP suite does not invoke the model.

Private cultural captures are not redistributed. Capture-dependent tests and
explicit replay factories require local files under ignored `reports/local/`;
missing captures skip those tests rather than invent positive results. Browser
acceptance scripts additionally require the documented loopback/CDP or Safari
WebDriver services specified in their source. Default CI checks run without
private documentation or release reports. The release checker fails closed when
local gate evidence is absent; `--report-only` reports that without failing CI.

The optional Qloo CLI tooling is isolated from the backend. Install with
`npm ci --prefix tools/qloo --ignore-scripts`. Its manifest pins the harness and
an agent override; authenticated/interactive compatibility must be checked
separately. `scripts/verify_qloo_tooling.py --help` describes its offline verifier.
No live calls are needed for normal build/tests.

## Code and licences

- `backend/app/`: FastAPI, server-only providers, authoritative rules and SQL saves.
- `client/Assets/`: Unity source, scenes, prefabs and locally bundled runtime art.
- `shared/schemas/`: versioned API contracts; regenerate with `scripts.export_contracts`.
- `backend/tests/`, `tests/`, `scripts/`: automated checks and explicit verification tools.

See [API integration](docs/API_INTEGRATION.md) and [security boundaries](docs/SECURITY.md).
Project source is [MIT licensed](LICENSE). Imported art/audio and other obligations
are listed in [third-party notices](THIRD_PARTY_NOTICES.md); original asset licences
and the selected-file manifest remain in `client/Assets/ThirdParty/Kenney/`.
