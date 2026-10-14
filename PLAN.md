# E-File Regression Suite — Plan

Status: planning agreed 2026-10-14 (second session). Supersedes the fixture-strategy
open question in the 10/14 planning memory — resolved below. Nothing here is built yet;
this is the design to build PLB-1243 through PLB-1248 against.

## Target environment

**LawBase_Design, Tyler stage. Not Sandbox, not Prod.** This matches where the real
e-file build work already happens (PJ, Interventions, Litigation, the 10/5 four-button
run) — Design is where the live exes and live Tyler stage integration actually are.

## Stack

| Piece | Choice | Why |
|---|---|---|
| Language/runner | Python 3.14 + `pytest` | Already the tool used to validate the defendant-name-split rule against 798 real rows (10/5). Gives clear pass/fail reporting, parametrization across flows/causes, and `-k`/`-m` filtering for `--flow pj`-style partial runs, none of which a pile of `.ps1` scripts does well. |
| DB access | `pyodbc` | Already installed on this machine, `ODBC Driver 17/18 for SQL Server` both present — zero new install risk. Gives typed query results to assert on directly, instead of parsing sqlcmd's pipe-delimited text output. |
| Wire XML | `lxml` (already installed) | Memory is explicit that regex/grep parsing of Tyler's XML caused real wrong conclusions (`<SimpleValue />` self-closing tags). Always parse with a real XML parser/namespace-aware xpath, never string matching. |
| Exe invocation | `subprocess`, calling the existing CLI flags | `TaxLit13EfileSubmit.exe` / `TaxLit13PJSubmit.exe` / the Interventions and Litigation exes already have `--probe-causes`, `--list-case-parties`, `--no-confirm`, etc. built in. No new instrumentation needed — the suite is a black-box caller of the real deployed exe, same as a human running it. |
| Fixtures/golden values | JSON files, one per flow + one pool registry | Plain, diffable, easy to review in a PR/commit — see `fixtures/` below. |

One new dependency to install: `pip install pytest`. Nothing else.

**Why black-box over a C# unit-test project added to the BatchFiling solution:** every real
bug this project has ever found (FilerType hardcode, Multiplier omitted at qty 1,
FilingAttorneyID category mismatch, mangled defendant names) was invisible to "it compiles"
and to `ErrorCode=0` — it only showed up by looking at the actual wire XML and the actual DB
write-back. A C# unit test that mocks Tyler or asserts on internal method return values would
have missed all four. The suite must stay at the black-box layer: real exe, real Tyler stage,
real DB.

## Location

`L:\Modules\EFiling\Tests\` — runnable from any machine that can already reach
`L:\Modules\EFiling` (which is how the exes themselves are already distributed), so the
suite works even when Aarshita isn't the one running it. This file and `TESTING_RULES.md`
live here too, not on Desktop, so nothing requires a side channel to find them.

## Three assertion layers (cheapest first — unchanged from the 10/14 plan)

1. **SQL-level** — PICK_LIST key shape, row counts, lookup values. No UI automation, no
   Tyler call. (PLB-1248.)
2. **Wire-level** — run the real exe against Design/stage, capture the actual outbound XML
   (`%LOCALAPPDATA%\TaxLit13EfileSubmit\last-reviewfiling-outbound.xml` or the per-team
   equivalent), assert specific fields against golden values. **This is the layer that
   matters most** — it's the one that would have caught FilerType, Multiplier, and
   FilingAttorneyID on day one instead of weeks/months later.
3. **DB-write** — after submission, query `TAXLIT13`/`TAXLIT13A` etc., confirm the written
   values (FilingStatus, EnvelopeNum, no LastError) match what was actually sent.

A flow test is not "done" until all three layers pass. `ErrorCode=0` alone proves nothing —
see `TESTING_RULES.md` rule 4.

## Fixture strategy: a curated pool of real causes, not synthetic per-run cases

Resolved per your call: use several already-real, already-verified cause numbers with
varied behavior, and treat "nothing broke on any of them" as the regression signal — a
case that already carries a filed TAXLIT13 row is exactly what a subsequent-filing test
needs, with zero setup. Concretely, the pool starts from causes **already proven live** in
past sessions rather than picking new ones blind:

| Cause | CaseSerial / court | Covers | Source |
|---|---|---|---|
| **202310045** | `harris:dccv152` | PJ subsequent; 11-plaintiff + 9-spelling-AKA party list (stresses party grouping) | env 327932/327949, [[lawbase-efile-pj-build]] |
| **202653957** | 1773097 / `harris:dccv270` | **All four flows** (PJ/Interventions/Lit-OP/Lit-existing), Constable + Secretary-of-State ServeBy branches, the Maria/Cynthia mangled-name regression check, has its own reset mechanism (`12_RESET_AND_ServeBy_Test.sql`, TAXLIT13 Serial 34-38) | 10/5 four-button run |
| **202582347** | — | Interventions' "Harris County NOT yet a party" creation path (`NewParty1`/`REFERENCE`), the one path the shared-case run above did *not* exercise | env 328386/328394/328403 |
| **671187** | — | Multi-petition CalcFee math (2 × $350 petitions = $878.68) | [[lawbase-efile-current-workflow]] |
| 202656147 (1767556) | — | **Excluded from the active pool** — stage lost all its party data between sessions with no code change (10/5 finding 3). Keep it only as a documented cautionary entry / occasional re-probe, never relied on. |
| TBD | — | A genuine Litigation existing-case *non-suit* example — not yet pinned to a real cause; pick one while building PLB-1247, don't guess now. |

**Fixture health check runs first, always.** `test_00_fixture_health.py` probes every
registered cause (`--probe-causes`, `--list-case-parties`) before any flow test touches it.
A dead fixture fails loudly as *"FIXTURE UNHEALTHY: re-pick cause X"* — distinct from a flow
failure — because a known-good cause rotting on stage (202656147) is a real, already-observed
failure mode, not a hypothetical one.

**One gap this model doesn't cover on its own:** regression on already-proven shapes, not
genuinely new creation paths. Litigation's new-case OP (PLB-1246) doesn't have a "subsequent"
precondition to begin with, so it keeps using a fresh-case SEED script per run (same pattern
as the existing `08_SEED_AllThreeTeams_SharedCase.sql`/`09_SEED_FourButtons_OneCase.sql`)
rather than the fixture pool — there's nothing to reuse for a flow whose whole point is
creating something from nothing.

The pool itself lives in `fixtures/causes.json` — cause, flow(s), what it proves, date last
verified healthy — so it's an auditable file, not tribal knowledge.

## Build order

1. **PLB-1243** — harness + runner skeleton: DB connection helper (pyodbc), exe-invocation
   wrapper, wire-XML capture + lxml diff helper, fixture-pool loader + health-check module,
   golden-file loader, pass/fail report. Everything else depends on this.
2. **PLB-1248** — SQL-level/PICK_LIST checks. Cheapest, no Tyler dependency, also exercises
   the harness's DB-query helper before anything wire-level is built on top of it.
3. **PLB-1244** — PJ, subsequent + service contacts. Simplest flow, clearest golden values
   already verified live (envelope 328389), lowest risk to shake out the wire-diff harness on.
4. **PLB-1245** — Interventions, subsequent. Reuses most of PJ's harness shape.
5. **PLB-1246** — Litigation new-case OP. Fresh-case path, no fixture pool involved.
6. **PLB-1247** — Litigation existing-case (judgment/dismissal/non-suit). Built last: most
   gating logic (cause-empty gate, "must declare NO parties"), and carries the one genuinely
   open bug (mangled defendant names) that the suite must mark `xfail` with a ticket
   reference rather than quietly pass or quietly fail the whole run — see
   `TESTING_RULES.md` rule 3.

## Explicitly out of scope

- No UI/client automation (clicking the real LawBase screen) — too fragile for the value,
  per the original 10/14 scoping call. The exes' own CLI flags are the entry point.
- No Sandbox, no Prod.
- No new Tyler-side test data creation beyond what's already in the fixture pool or what a
  fresh-case SEED script creates for Litigation OP.
