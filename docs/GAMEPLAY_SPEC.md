# Infinite Stories: The Last Light — playable investigation specification

Player fantasy: a stranger curates the city's last memories before the dawn tram
leaves. Escape by proving a cultural connection, not by guessing a password.

**Loop:** choose up to five supported favourites → resolve actual entities and
related results → follow Mara's route → investigate a screening note using the
Scanner → earn Ivo's rhythm → collect the corresponding memory at Sera's shop →
choose a privacy promise → present supported affinity to the Curator → choose
leaving together or staying as keeper. Failed claims explain the missing evidence.

**Economy (new saves: `conversation-v1`):** start with zero of twelve
conversations spent. Opening/inspecting a resident or the Curator, choosing a
resident option directly, or successfully completing an ordinary free-form
resident dialogue enters an encounter and spends one visit. Continuing the same
encounter is free, including multiple messages, clues and Curator proofs. Failed
model calls and rejected commands do not spend visits. Evidence-only tool reads
are free. Scanner reads, journal, movement, travel, autosaves, retries and receipt
replay never independently spend visits. Scanner Record obeys the same rules as
the underlying server choice: a resident/gate choice may enter an encounter.

An encounter closes on confirmed movement more than three tiles from its resident
(the interaction radius is two tiles), travel, or talking to another resident.
Closing dialogue UI alone does not close the encounter. At twelve spent visits,
the current encounter may finish, including all valid proofs and an ending at
the Curator. Leaving its radius or travelling without success produces dawn;
starting any further encounter produces dawn without granting its outcome.
There is no wall-clock timeout or charge per message. Invalid actions remain
invalid and cannot spend visits or escape a dawn ending. The normal success
witness uses four conversations. Existing saves with no `visit_rules` field
explicitly retain `travel-v1`, starting at one and charging only travel. No
existing save is migrated or reset.

**Activation:** new authored and cultural runs must have an executable success
witness before persistence. The bounded production planner resolves prerequisites,
walks real collision paths, crosses real portals and applies actual engine choices
through cross-category proofs and a success ending. Connectivity alone is
insufficient. At most three deterministic candidates are tried from the same
validated evidence, rotating selected recommendations after the first candidate;
no regeneration fetches or invents provider results. Search is capped at128 goals
per candidate. Exhaustion returns recoverable `CITY_UNSOLVABLE` without activating
a run. Evidence/base-chapter hashes, candidate index, witness hash, steps, terminal
visits and ending are saved atomically with the state. Cancelled reservations
cannot publish late results. Provider-free resume checks the persisted validation
against saved evidence and the chapter; it never regenerates existing saves.

| Venue | Resident and gameplay purpose |
| --- | --- |
| Side A record bar | Mara, protective keeper of forgotten B-sides. Gives the map and explains evidence versus interpretation; hints reference this run's saved favourite. |
| Afterimage cinema | Ivo, precise, wry projectionist. Screening notes ask which actual result belongs to the saved cross-category recommendation set. Prove all notes before earning the rhythm. |
| Thread & Echo boutique | Sera, consent-conscious collector/tailor. Record the matching memory cards and choose sharing or guarding private letters. |
| Last Gate | Curator, skeptical but fair. With the three memories, present each saved seed→selected entity as aggregate affinity. Unsupported collaboration/personality claims fail without progress loss. Then choose an ending. |

**Scanner's five operations:** Search the run's saved catalogue by name; Related
results for a selected saved seed; Inspect selected entity/tags/provenance; Progress
through the clue chain; Record the nearby server-offered discovery. The catalogue
is explicitly saved evidence, not a new live search. New favourites are resolved at
new-game creation by the production provider. No provider calls occur merely from
opening the Scanner. The actual agent now selects the five named typed backend tools with distinct
arguments/results, observes real saved evidence/state and can chain up to two tools
per turn. Discovery recording commits through the existing authoritative action
receipt. Ordinary dialogue, movement and authored quest choices retain the typed
gameplay proposal path. Factual past commitments are rendered from confirmed
choice IDs/flags; generated dialogue never becomes evidence of a player decision.


**Authority and compatibility:** retain session/action/turn APIs, receipts, guest
ownership and persistence. Use the existing cultural `rule_version` field to opt
new production contexts into `cultural-investigation-v2`. Existing `cultural-cards-v1`
saves retain their original map/rules. New trace/proof flags are earned only through
server-issued choices containing actual normalized entity identifiers. Versioning
is necessary because silently changing prerequisites or walls could break old saves.

**Journal:** connect favourite → returned result → screening trace → memory card →
Curator proof. Distinguish confirmed discoveries, missing steps and creative setting.
Taste Card rewards the actual choices, supporting cultural pair(s), privacy promise
and ending. Never infer player identity or treat affinity as collaboration evidence.

**Completion reward (`taste-card-v1`):** the engine builds `state.taste_card` exactly
once on success/keeper/dawn, in the same transaction as the terminal state/receipt.
It saves canonical resolved favourites; confirmed story discoveries; encountered
seed entities and selected results earned through trace/memory/proof flags; their
actual directed saved recommendation provenance; a profile; and at most six try-next
picks. Catalogue reads alone do not claim a confirmed discovery. No new provider or
model requests occur. Refresh/restart returns the saved card, not a newly sampled
reward. Old completed saves lacking the field receive a pure deterministic v1 view;
their stored state, version, receipt and clock rules are not silently migrated.

Profile is an **application exploration heuristic, not Qloo classification or
personality**. With a confirmed thread, one source category maps artist→Sound-to-
screen explorer, movie→Screen-to-sound explorer, brand→Design-to-screen explorer,
video game→Play-to-screen explorer; mixed directions yield Cross-media explorer.
Without a confirmed thread the result is First-light explorer and explicitly
insufficient for a cultural taste classification. Up to three actual encountered
entity tag labels support the description, ordered by descending number of entities
carrying each tag ID then ascending ID; each entity counts once per tag. Sparse tags
remain unavailable: never infer a missing genre. Synthetic control receives the
authored Lantern storyteller label, explicitly not a cultural taste measurement.

Try-next picks use only saved recommendation membership; exclude every selected
favourite and confirmed encountered entity, deduplicate by UUID, sort sources/targets
by UUID and cap at six. Each pick retains its source/target/category and the original
request provenance. Copy explains aggregate affinity only; no invented rationale,
reverse edge, personal trait or claim of collaboration. Empty evidence gives a clear
limited/empty state. Dawn can still suggest saved, undiscovered results; it does not
retroactively mark them as discovered.

**Playable comparison:** new `generic_control` sessions are separate immutable-mode
saves, never in-place conversions of a cultural game. The title and Scanner offer
Qloo off / on; Unity bookmarks each mode and resumes the existing paired save on
return. Pending operations must be reconciled before switching; position is flushed
first. Different players use distinct bearer owners/browser profiles; sessions and
creation/action receipts remain scoped to ownership. A second player should use a separate browser profile, or normal versus private
profiles, not share the resume token. Two private windows in one private session
may share storage and should not be treated as separate player identities.

`synthetic-control-v1` has a constant saved seed `last-light-control-v1`. Its invented
record The Lantern Waltz and invented film Paper Moon Tram share an **authored** motif,
three amber circles. Route: Mara map → boutique sleeve note → Ivo rhythm → record-bar
ticket display → Sera promise → Curator motif proof → ending. This differs from the
saved-Qloo candidate's note/card venues, cultural UUID graph, understanding gates and
affinity-proof requirements. It intentionally does not personalize culture from the
selected favourites. The motif answer is an authored option, not a semantic judgement
of real culture; the engine still requires its clues and twelve-visit economy. It is
not a Qloo-disabled relabelling of real data, nor a claim that generic clues are live.

Synthetic control has its own strict schema, **no CulturalContext, no CulturalEntity
UUIDs and no CulturalRequest records**. Synthetic links cannot enter Qloo tools or
satisfy cultural proof choices. Scanner shows invented props separately; agent
cultural tools correctly return no provider evidence. Journal/HUD/card explicitly
identify synthetic content. New control runs pass the same executable solver and
bind their initial gameplay to the saved activation fingerprint. Legacy authored
runs retain their old chapter and remain available through the existing API/bridge.
The control's story motif proof deliberately has no cultural-understanding gate;
the comparison demonstrates the difference between authored answers and validated
cultural evidence, not different decorative labels.

**Presentation:** Unity owns the world and interaction. HTML only hosts it and
provides secondary access controls/diagnostics. Keep the world-first composition;
make venue floor plans and furnishing footprints distinct for v2, retaining reachable
spawns/NPCs/cards. Reuse licensed16px art, original matching props, restrained amber
lights, rain, directional actors and optional muted ambience. No paid assets.

**Controls/tutorial:** WASD/arrows move, E inspects nearby targets, mouse chooses;
J opens Journal, C opens Scanner, Esc closes a context panel or opens Menu. First-run
help explains free investigation versus paid-in-visits conversation encounters and the four-stop route.
It is an authored tutorial, not model output. It does not change authoritative progress.

**Acceptance journey:** fresh cultural run/tutorial; Mara map; saved-catalogue
search/related/inspection; reject unsupported screening claim; record correct note;
Ivo rhythm; Sera memory/privacy choice; reject unsupported Curator claim; record
actual affinity proof; success/Taste Card; refresh/resume and backend restart.
Also exercise12-conversation dawn, both success choices, model outage/empty cultural results,
idempotent duplicate/lost responses, and recovery. Separate local inference,
provider replay, controlled failures and browser evidence. No live provider calls.

Process references reviewed: [Frosthold prompt](https://playagain.ai/games/frosthold),
[Manus Game Maker](https://manus.im/tools/ai-game-maker), and
[Manus Game Dev philosophy](https://www.manus.im/pl/blog/introducing-game-developer).
Applied principles: explicit verbs and dependencies, scoped campaign, readable
feedback, short onboarding, and complete self-playtesting. No setting/art/mechanics
were copied, no account created and no generation service invoked.


## Cultural understanding (new `cultural-understanding-v3` runs)

Saved v1/v2 campaigns keep their original clue rules; no save migration occurs.
New production Qloo contexts use v3. The Scanner's saved catalogue is accessible
from arrival, so no outside cultural knowledge is needed. Resident text exposes
the current seed/result and asks for an explanation in the player's own words.

| Encounter | Discoverable evidence / prerequisites | Understanding needed | Clue |
| --- | --- | --- | --- |
| Mara, record bar | First saved seed and selected cross-category recommendation, available in Scanner from arrival | Explain this recommendation as aggregate affinity and distinguish it from a collaboration or personal identity claim | map |
| Ivo, cinema | map and all recorded screening traces; same first saved pair | Explain what the screening evidence supports and what it does not establish | rhythm |
| Sera, boutique | rhythm and all collected cultural cards | Explain the affinity, distinguish our fictional setting from provider fact, and explicitly choose a current sharing/guarding promise | chronicle and chosen promise |
| Curator, gate | map, rhythm, chronicle, relevant card; next actual saved pair in sequence | Explain the cross-category affinity and its limits; names/IDs alone are insufficient | proof for that link; all proofs still required before an ending |

A local model first interprets intent, then classifies a committed explanation as
supported, incomplete, unsupported or unclear. It returns strict fields, actual
UUID references and quotations constrained to submitted text. There is no exact
answer string or keyword acceptance test. Incomplete/unclear attempts receive
constructive hints, unsupported claims explain the evidentiary limit, and no
classification writes state directly.

The engine rechecks the current revision, location/reach, prerequisites, canonical
choice, selected pair/direction/category, validated saved provenance, evidence
hash and actual submitted text before accepting a supported assessment. Sera
also requires an explicit current choice and fiction/evidence separation. Each
accepted assessment is persisted as a typed read-only record with the outcome;
commands cannot carry certificates. Independently of model confidence, a bare enumeration of the run's entity names/IDs has no explanatory proposition and is rejected. This structural veto cannot accept an answer or replace semantic interpretation. A separate local semantic review classifies the actual quoted spans: a name list is not a connection explanation, a request/promise is not an evidence limitation, and a fictional setting must not be asserted as provider fact. The connection review checks affinity and limits; a focused keeper review owns Sera's additional fiction/current-promise criteria. All required criteria must pass. Duplicate turns replay the durable receipt.
The engine's existing CAS and ownership checks protect concurrent attempts.

A first unsuccessful *completed* resident explanation may enter an encounter;
continuations are free. Malformed/unavailable model responses do not spend a
visit. All final-visit and dawn rules above remain authoritative. Model outages
never silently grant clues or substitute authored success.

The activation solver uses an explicitly ideal-player explanation witness to
prove a feasible evidence-accessible route under these rules. It is not an LLM
quality test and is never used to interpret a player's request. New run state
contains no accepted understanding records until real turns are confirmed.
Semantic truth is a measured model capability: UUID/text checks cannot formally
prove that an arbitrary natural-language explanation means what a classifier says.
The separate local evaluation must remain a release gate.

Current privacy consent is distinct from grammatical tense: an unconditional
pledge to keep the letters safe counts, while claiming an earlier agreement does
not. A keeper specialist extracts the player's actual choice clause; the engine
independently vetoes a past-history basis. An actual explanation to a confirmed
active resident question can enter the understanding workflow even if its
initial tool selection is Inspect. Ordinary factual questions still use the
five read/discovery tools; no extra clue-taking sentence is required.

## Saved procedural cultural cities (current new runs)

New conversation-v1 cultural runs now save a `saved-cultural-city-v1` plan. This
section supersedes fixed clue placements described for legacy investigations.
Existing saves without a plan keep their original geometry and rules; resume does
not generate, migrate or reroll a city.

The four venue identities and Mara→Ivo→Sera resident milestones remain authored.
Variation is in the actual investigation: selected recommendation entities,
resident evidence assignments, clue locations/coordinates, prerequisite chains,
ordered Curator proofs, and an additional bidirectional street passage where the
chosen template includes one. The three route families distribute notes/cards
among the record bar, cinema and boutique. The last gate remains the conclusion.
The authored floor tilemaps are retained; this is not arbitrary terrain generation.

A seed is SHA256 of canonical normalized favourite entities and the available
recommendation catalogue (tags/results sorted; no timestamps, keys or request IDs).
Equal favourites/catalogue produce the same seed. A saved plan records seed,
version, candidate, template, proof order, clue venues, resident assignments,
metadata estimates and shortcut. Reopening a save uses that plan, not fresh data.
Same preferences/catalogue intentionally do not generate a new city on refresh.

For multiple favourites, trace/card chains follow the chosen proof order in the
nonclassic templates; the classic template permits independent collection. Cards
need rhythm and their own recorded trace. Ivo needs all traces and Sera all cards.
Mara discusses the first selected thread; Ivo the last; Sera a deterministic middle
thread when there are at least three. Their understanding questions refer to those
actual saved entities. The Curator exposes the next saved proof in plan order.
These prerequisite/route edges are authored game logic, NOT extra Qloo relations.

### Far but connected: application tag contrast

For favourite A and actual returned recommendation B, let D be the intersection of
nonempty tag `type` domains present on both entities. Let TA/TB contain their tag
IDs in D. If their union is nonempty, contrast = 1 − |TA ∩ TB| / |TA ∪ TB|, rounded
to six decimals. Otherwise contrast is null and metadata status is `unknown`.
Different categories or incomparable/missing tag schemas alone do not imply high
distance. Known higher contrast is preferred; ties use the stable seed/real entity
ID hash. If all metadata is unknown, the seeded choice is explicitly NOT a distance
measurement. Fallback candidates can select other actual saved recommendations.

This is a coarse application heuristic, not a Qloo score, validated measure of
novelty, or a fact about the player's personality/familiarity. Even shared tag types
can be broad taxonomies across media. A zero value means tag overlap, not proof the
player knows the work; a high value means tag contrast, not guaranteed unfamiliarity.
No missing tags are invented. Resident text distinguishes the estimate/unknown
metadata from the actual saved affinity. No blanket "far" claim is made for sparse
catalogues. The direct connection remains evidenced regardless of tag coverage.

Only exact directed saved recommendation edges are used. Recorded paths are
bounded to two hops/six examples. A two-hop path does not establish transitive
endpoint affinity; every selected Curator proof still requires a direct saved
cross-category recommendation. No inverse relationship is inferred.

### Activation and recovery

The existing production engine solver executes each complete candidate before
activation, with ideal-player understanding witnesses only for feasibility. It
must reach a valid ending in at most twelve conversations. At most THREE attempts
use already fetched validated evidence; regeneration has no provider/model calls.
Exhaustion returns recoverable `CITY_UNSOLVABLE`, leaves valid saves untouched and
retains existing cancellation/late-worker/idempotency guards. Initial saved runs
contain no solver-earned flags, receipts or understanding grants.

Certificates bind evidence, base chapter, saved plan and the initial generated
GAMEPLAY definition (geometry, portals, choices, prerequisites/effects). Progress
and harmless presentation copy are excluded from the generated-gameplay hash.
Corrupt/mismatched seeds/plans are rejected safely, never silently regenerated.
Future rule/generator changes need explicit version compatibility.

All explicitly selected favourite IDs are excluded from central-culture candidates,
including a favourite returned by another seed's recommendation list. If a link has
no remaining candidate, bounded generation fails safely instead of calling a known
favourite a discovery. This does not imply the player is unfamiliar with every
unselected entity. Tag contrast is measured against each link's originating seed,
not asserted as a global personal-familiarity score across all preferences.
