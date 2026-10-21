# Infinite Stories: The Last Light — playable investigation specification

Player fantasy: a stranger curates the city's last memories before the dawn tram
leaves. Escape by proving a cultural connection, not by guessing a password.

**Loop:** choose up to five supported favourites → resolve actual entities and
related results → follow Mara's route → investigate a screening note using the
Scanner → earn Ivo's rhythm → collect the corresponding memory at Sera's shop →
choose a privacy promise → present supported affinity to the Curator → choose
leaving together or staying as keeper. Failed claims explain the missing evidence.

**Economy:** the starting district is visit1. Only confirmed portal travel spends
one visit. Movement, conversations, Scanner operations, agent questions and wrong
answers cost no visits. After12 visits an attempted further trip produces a gentle
dawn ending. The direct successful route is four visits. Optional kindness and
privacy affect the ending. No combat or survival-resource system is added.

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
opening the Scanner. The actual agent retains its evidence tool and typed proposals. Its eligible
actions include explicitly conditional token/ending effects; these are not
current possessions. Engine validation filters the menu and commits effects.

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

**Presentation:** Unity owns the world and interaction. HTML only hosts it and
provides secondary access controls/diagnostics. Keep the world-first composition;
make venue floor plans and furnishing footprints distinct for v2, retaining reachable
spawns/NPCs/cards. Reuse licensed16px art, original matching props, restrained amber
lights, rain, directional actors and optional muted ambience. No paid assets.

**Controls/tutorial:** WASD/arrows move, E inspects nearby targets, mouse chooses;
J opens Journal, C opens Scanner, Esc closes a context panel or opens Menu. First-run
help explains free investigation versus paid-in-visits travel and the four-stop route.
It is an authored tutorial, not model output. It does not change authoritative progress.

**Acceptance journey:** fresh cultural run/tutorial; Mara map; saved-catalogue
search/related/inspection; reject unsupported screening claim; record correct note;
Ivo rhythm; Sera memory/privacy choice; reject unsupported Curator claim; record
actual affinity proof; success/Taste Card; refresh/resume and backend restart.
Also exercise12-visit dawn, both success choices, model outage/empty cultural results,
idempotent duplicate/lost responses, and recovery. Separate local inference,
provider replay, controlled failures and browser evidence. No live provider calls.

Process references reviewed: [Frosthold prompt](https://playagain.ai/games/frosthold),
[Manus Game Maker](https://manus.im/tools/ai-game-maker), and
[Manus Game Dev philosophy](https://www.manus.im/pl/blog/introducing-game-developer).
Applied principles: explicit verbs and dependencies, scoped campaign, readable
feedback, short onboarding, and complete self-playtesting. No setting/art/mechanics
were copied, no account created and no generation service invoked.
