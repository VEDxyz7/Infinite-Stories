# API integration

The authoritative contract is [shared/schemas/openapi.json](../shared/schemas/openapi.json).
Regenerate with `.venv/bin/python -m scripts.export_contracts`; `--check` detects
schema drift. Interactive documentation is available at the backend's `/docs`.

| Route | Purpose |
| --- | --- |
| GET `/healthz` | Process liveness; no provider calls |
| GET `/readyz` | Storage/configuration readiness; not complete game acceptance |
| GET `/v1/capabilities` | Explicit authored/cultural/model availability and verification mode |
| GET `/v1/chapter` | Original authored chapter |
| POST `/v1/sessions` | Bearer-owned, request-ID-idempotent authored or cultural session creation |
| GET `/v1/sessions/{id}` | Owned, unexpired confirmed snapshot |
| POST `/v1/sessions/{id}/actions` | Validated command with expected revision and request ID |
| POST `/v1/sessions/{id}/turns` | Optional configured Game Master action interpretation |
| DELETE `/v1/sessions/{id}` | Revoke access; not immediate physical deletion |

The client generates a cryptographically random guest bearer credential and
keeps it private. Send it through `Authorization: Bearer …`, never URLs. Reuse
the **same request ID** when confirming an uncertain write; a new ID is a new
operation. The server checks ownership, expected revision, proximity, terrain,
choice prerequisites and ending rules before committing state. Reload confirmed
state after a stale-revision response. Client flags/positions are not authoritative.

Errors contain `error.code`, a safe `message` and correlation `request_id`.
Typical statuses:401 missing/malformed ownership,404 unavailable/foreign/expired
session,409 invalid/stale action,413 oversized body,422 invalid schema,
429 request/model limits and503 storage/provider unavailability. Error handling
must preserve the last confirmed save rather than claim an unconfirmed success.

## Cultural sessions

Supported input categories are `artist`, `movie`, `brand`, `videogame`.
Only movie inputs target artists; the others target films. Books are rejected.
Player-selected ambiguous identities require a returned candidate UUID and a
new deliberate creation request; the client must not guess an entity identifier.

The server-only adapter uses GET `https://hackathon.api.qloo.com/search` with
`query`, `types=urn:entity:<category>` and `take=5`. A verified entity feeds GET
`/v2/insights` with `filter.type=urn:entity:<target>`,
`signal.interests.entities=<UUID>` and `take=5`. Search and Insights have distinct
response containers; normalization preserves valid IDs, categories, useful
metadata/tags and request provenance. This context drives required cultural
objectives and original story settings, then persists with the session.

Calls require private server credentials and explicit `IS_QLOO_CALLS_ALLOWED`.
`IS_QLOO_DAILY_REQUESTS`, `IS_QLOO_MIN_INTERVAL` and `IS_QLOO_CACHE_SECONDS` are
application controls, not verified vendor quotas or permission to make calls.
The adapter does not retry or follow redirects. Ambiguity, unresolved input,
empty/malformed data, authentication, rate limits, HTTP errors, timeout, network
failure and application budgets have distinct safe error codes. Failed provider
work cannot overwrite confirmed world/quest state. Resume uses persisted context
without refreshing the provider. Never publish raw responses or private captures
without applicable redistribution rights.

## Game Master

`IS_LLM_PROVIDER=ollama` uses the fixed private loopback runtime; the separately
configured `openai` adapter requires a server key and paid-call authorization.
Both require explicit model/call configuration. There is no automatic hosted or
paid overflow, download or provider substitution.

The local agent selects a typed evidence-reading or gameplay-proposal tool. The
backend executes it against actual saved evidence or legal nearby actions;
model memory is not verified cultural evidence. Schema validation and the engine
preview precede transactional revalidation. The model cannot mutate arbitrary
flags, positions, inventory or endings. Fictional dialogue is distinguished from
provider facts and canonical engine narration.

Turns have bounded input/output, timeouts, admission limits and durable budgets.
Duplicate IDs replay receipts without new inference; failed/pending reservations
do not cause automatic repeated calls. Saves remain recoverable when inference
is unavailable. The default configuration makes no model calls. See the root
[README](../README.md) for setup and [security guide](SECURITY.md) for deployment boundaries.
