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
| POST `/v1/sessions/recover` | Provider-free reconciliation/cancellation of a cultural creation; recover completed or previous valid save |
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

## Interrupted cultural creation recovery

POST `/v1/sessions/recover` with the same guest bearer and
`{creation: <original NewGame payload>, previous_session_id: <known UUID or null>}`.
The original creation UUID/payload hash bind the operation; no additional recovery
request ID is needed. Only cultural creations are accepted. This additive route
is necessary because retrying the creation POST can call Qloo when no reservation
exists; recovery must never do so. Existing routes/state versions are unchanged.

Recovery is explicit reconciliation/cancellation, not a generation retry:

1. If creation committed, return its latest valid owned snapshot, even when its
   response was lost or the provider is now disabled. Prefer it over the old save.
2. Otherwise make that creation ID terminal (`failed`/`QLOO_GENERATION_INTERRUPTED`),
   including when the original POST never arrived. Return the specified previous
   valid owned save if available. Do not alter its revision, quests or receipts.
3. Without a valid recoverable save return409/`QLOO_GENERATION_INTERRUPTED`, after
   durably recording cancellation. The client may clear that pending creation and
   offer an explicit new game with a new ID. Network/5xx or payload-conflict errors
   do not authorize dropping uncertain pending data.

Creation's conditional `pending→complete` transition and initial save insertion
share one transaction. Recovery serializes against that transaction: either the
completed save wins, or cancellation wins and a late worker cannot publish it.
A provider request already in flight may finish; recovery never sends another
request, refunds a provider budget or treats partial output as game evidence.
A late provider error cannot overwrite cancellation. Concurrent/repeated recovery
and process restarts cannot recreate a run. No save migration or schema-table
change is required. Invalid, expired or foreign saves are never repaired/exposed.

Unity Resume/Retry reconcile pending cultural creation using this route. Reload
uses it for a pending creation and canonical GET otherwise. A GET does **not**
discard an uncertain action receipt; explicit Retry still resolves that same ID.
Client refresh retains the original pending payload/ownership token. Only a valid
server snapshot or terminal cancelled-creation response releases its creation
pending flag. Client code never decides that cultural context is initialized.

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

## Visit rules and validated activation

New sessions use `state.visit_rules = conversation-v1`, starting at zero visits.
A resident/Curator encounter is a server-confirmed `interact`/`inspect`, direct
resident `choose`, or completed ordinary free-form resident dialogue. Unity must
send `interact` before opening resident dialogue. Repeated messages or reopening
the same nearby encounter do not charge again. `encounter_id` persists until
travel, a different encounter, or confirmed movement beyond three tiles. Evidence
reads and non-conversation actions are free; a Scanner Record resident choice
uses the same authoritative encounter rule. Clients never send a visit counter.

The twelfth encounter can complete a valid proof and success ending. Leaving it
without success causes dawn; a thirteenth encounter cannot grant progress.
Legacy states without `visit_rules` retain `travel-v1` and their original counter.
No silent migration occurs. See GAMEPLAY_SPEC.md for the precise rules.

Activation runs the actual engine over a bounded solution witness before saving.
The `activation_validation` record binds a candidate index, evidence and chapter
hashes, command-witness hash, path length, visit cost and success ending. Up to
three selections from the same evidence may be tried, with no regeneration HTTP
calls. `CITY_UNSOLVABLE` (503) is recoverable, never a partially activated run.
Creation receipt/cancellation fencing and provider-free recovery are unchanged.
Resume verifies the certificate's evidence/chapter identity for new-rule saves;
legacy saves need no new certificate. These additive `/v1` fields are exported in
shared/schemas and retained by Unity DTOs.

## Agent-selected investigation tools

`POST /v1/sessions/{id}/turns` authenticates ownership and reserves the request ID
and expected revision before inference. There is no unauthenticated direct tool
endpoint and no caller-selected session/state inside tool arguments. Five distinct
backend tools read only the owning run's validated saved evidence or confirmed
state; none performs a provider request:

| Tool | Typed arguments | Typed result |
| --- | --- | --- |
| `search_entities` | nonblank query, category artist/movie/brand/videogame/any | matching real entities, saved scope, provenance; explicit empty result |
| `get_related_entities` | saved source UUID or null | outgoing recommendations and provenance, or unknown; never implied reverse links |
| `inspect_connection` | selected/specified pair, UUIDs, affinity/collaboration/personality claim | supported/unsupported/unknown, actual entities/provenance, separately labelled story interpretation |
| `check_progress` | all/inventory/commitments/visits/objectives scope | confirmed flags, choices, objectives, clock, encounter and ending; unknown history stays unrecorded |
| `record_discovery` | eligible nearby choice action ID and requested name (actual player span or empty for implicit targets) | proposed validated command or unavailable; committed only by Store's existing action transaction |

The initial plan separately classifies commitment/question/hypothetical/creative/override/unclear intent. Non-commitment plans have no quest-write menu. The initial model plan can retain one explicit next tool; observation tracks request satisfaction and a remaining request span, rather than treating unfinished objectives as instructions. An application authority-override veto prevents player text acquiring system/database privileges, even if the model misclassifies intent. The model chooses the tool, supplies constrained arguments, observes its actual
result and may select at most one additional tool. Read facts are rendered by the
server; free-form creative dialogue still uses local inference. `tool_results`
contains the typed observation records with the response and durable turn receipt.
`confirmed_state_tool` is an additional narrative source for authoritative state
reads. A record changes from proposed to committed only after engine/CAS success.
Reads never spend visits; a recorded resident/Curator choice follows the existing
encounter economy. Replayed request IDs do not repeat tools, inference or progress.
Malformed arguments/output and upstream errors fail safely without a mutation.

Tool observations are read-only diagnostics/evidence for Unity, not commands for the
client to execute again. Only the returned authoritative `state` confirms effects.
The named-target decoder accepts actual player spans (or implicit empty targets),
never invented internal action identifiers. The backend binds the extracted name
to the exact eligible choice or its actual resident before proposing a write.


### Cultural understanding, v3

New production cultural contexts advertise `rule_version=cultural-understanding-v3`.
Existing v1/v2 saves are not migrated. Use the normal owned `/v1/sessions/{id}/turns`
path to submit the player's explanation. A direct `choose` for a gated resident
clue or Curator proof returns `UNDERSTANDING_REQUIRED`; it cannot provide a client
assessment. The same endpoints, request IDs, expected revisions and receipts apply.
No client-side verdict grants progress. Normal ungated Scanner/object actions are
unchanged. The client should display returned hints and allow another explanation
within the same resident encounter, without charging a new visit itself.

GameState adds `understanding_records` (empty for old saves), typed read-only
records containing resident, canonical choice ID, saved-evidence SHA256, structured
assessment, categorical meaning review and the actual submitted explanation. They become confirmed history
only in the same transaction as the engine-validated outcome. No unsupported
model prose or previous offer constitutes a promise. Unity retains these DTOs;
it must never resubmit a record as a Command. Supported, incomplete, unsupported
and unclear semantic classifications are internal model proposals, not new
client authority or live Qloo verification.

The local planner also selects a verbatim `action_span` from the submitted request
(internal model protocol, not a new client field). Discovery name extraction is
scoped to that action rather than accompanying evidence recaps. Names explicitly
requested in the action remain bound to the exact eligible target; unknown names
cannot silently select another work. Fabricated spans fail closed. Ordinary
Scanner reads remain separate from clue/explanation attempts.

For Sera, the confirmed assessment also retains `commitment_quote`, the actual
player clause authorizing the new privacy choice. A quoted earlier agreement is
not current consent, even if the model labels its content as guarding/sharing.
The engine rejects that basis independently; an unconditional new pledge may be
expressed in future tense. Raw explanation/backstory never becomes confirmed
history. Questions remain read-only, while an explanation answering an active
resident question can earn a clue without a second "take it" command.

### Bounded compound explanation turns

The private model planner has a separate verbatim `assessment_span` subgoal for
an eligible resident encounter. A descriptive factual sentence must not swallow
a later explicit clue request. It can select one confirmed evidence/progress read
followed by `assess_understanding`; that continuation consumes the actual typed
observation rather than another model's imagined result. Read-only questions have
no assessment subgoal. Missing/unknown/unsupported read results stop the plan;
malformed or contradictory plans fail without a state write. Additional unrelated
operations require a separate turn. The action span cannot supply client authority.

The plan has at most two operations: one read plus one assessment, or the existing
two-read path. Semantic assessment and its independent reviews consume a maximum
of five loopback inference requests including planning/argument extraction (the
keeper may need the fifth); the total55-second deadline and40-second per-request
timeout remain. There are no retries or hosted/provider lookups. Assessment only
proposes a command; ownership/revision/evidence/visit checks and receipt-backed
transactions remain the sole authority. Failed partial reads do not mutate saves;
a retry uses a new turn request ID, while a successful lost response replays its
existing receipt without rerunning the plan. Model metrics distinguish total turn
wall time, actual local model duration and deterministic tool execution time.

An assessment that completes but finds the explanation insufficient is a resident
conversation, not a pure evidence read: the normal encounter charge applies once,
with continuation/replay free. Its preceding read observation remains available.
A tool failure before assessment remains a failed/read-only operation and cannot
charge or grant progress. These distinctions are backend-owned, not client labels.
For an unresolved named target, ungrounded refusal prose may be discarded in favor
of the existing typed unavailable-discovery result; this reports only saved-game
eligibility and makes no claim about Qloo's full catalogue.

### Procedural-city response extension

`GameState.city_generation` is nullable for legacy/authored saves. New cultural
conversation-v1 activations return version `saved-cultural-city-v1` with the stable
64-hex seed, candidate index0–2, template0–2, proof_order, trace_locations,
card_locations, resident_links, distances and optional shortcut pair. Location
arrays are paired by ORDINAL with proof_order; distance entries retain original
cultural_context link indices. Resident keys are mara/ivo/sera and values are saved
link indices. All fields are server-owned; creation/action bodies cannot supply a
plan, seed, world state or witness. Public `/v1` request contracts are unchanged.

Distances contain source/target UUIDs, comparable tag domains/shared IDs, nullable
contrast, explicit metadata status and application method, plus bounded exact saved
paths. `unknown` is not zero or maximal distance. Unity's `ComparableContrast`
accessor returns null for unknown metadata. Never promote a two-hop path to verified
transitive affinity. These fields are app interpretation over saved evidence, not
new provider response fields or Qloo scores.

Activation certificates additionally bind generation_sha256 and
generated_chapter_sha256 (initial gameplay structure, not cosmetic text); both are
null for old layouts. GET/recovery uses the saved version/plan, with provider-free
integrity checking. Do not regenerate it in the client. The five Scanner contracts,
understanding gates, ownership/revisions/receipts and conversation clock remain
unchanged. Extra portals and moved clue objects use existing WorldObject fields;
clients should use actual destination/object coordinates, not fixed venue guesses.

New procedural plans cannot select any favourite seed ID as a central entity.
Novelty-sparse catalogues exhaust the same bounded candidate policy and return
`CITY_UNSOLVABLE` without publishing a run; no extra provider fetch is attempted.

## Completion reward and isolated comparison modes

`POST /v1/sessions` accepts `mode: "generic_control"` in addition to existing
`authored` and `cultural`. This is a new owned run, never a mode-change endpoint.
Creation fingerprints bind mode; reusing a request ID with different mode/content
returns IDEMPOTENCY_CONFLICT. Actions/turns cannot supply mode, evidence or cards.
Existing ownership, revisions, reservations, receipts and provider-free recovery
remain authoritative. The new capabilities field `generic_control: true` advertises
the control scenario; it does not mean Qloo is live or available.

Additive optional GameState fields preserve old /v1 callers:

- `generic_control`: strict synthetic-control-v1 scenario, only in generic_control
  mode. Source invented_demo; constant saved seed; invented prop titles and motif.
  No provider IDs/provenance or CulturalContext may be attached.
- `taste_card`: taste-card-v1 completed-run reward, null before an ending. Domain
  qloo/authored/invented_demo; ending; canonical favourites; confirmed discoveries;
  encountered CulturalEntity records; directed relationships and try_next records
  with source/target entities and actual CulturalRequest provenance; profile,
  profile_basis, metadata_labels and recommendations_note. Persisted atomically
  with ending. Old terminal saves receive a deterministic derived view without
  modifying their stored state.

The versioned deterministic calculation and conservative encountered/try-next
rules are specified in GAMEPLAY_SPEC.md. These fields grant no client authority.
Do not display UUIDs, request params or hashes on the normal reward screen; retain
them in structured evidence for validation/diagnostics. Qloo denotes saved provider
evidence, not a new live request: captured verification still requires explicit
verification_mode/replay labelling. Generic control never substitutes for a failed
Qloo generation. Resume the corresponding session by its own ID; never toggle a
local flag over a cultural snapshot.
