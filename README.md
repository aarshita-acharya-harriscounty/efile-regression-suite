# E-File Regression Suite

Black-box regression tests for the four live LawBase e-filing flows (PJ, Interventions,
Litigation new-case, Litigation existing-case) against `LawBase_Design` + Tyler stage.

Read these in order before touching anything:

1. [`PLAN.md`](PLAN.md) — stack, fixture strategy, build order, Jira tickets (PLB-1243–1248).
2. [`HARNESS_SCOPE.md`](HARNESS_SCOPE.md) — exactly which exe flags, tables, and wire fields
   are in scope. Scoped deliberately to what's live today, not the certification-era surface.
3. [`TESTING_RULES.md`](TESTING_RULES.md) — the rules that keep this suite honest. Read before
   touching a fixture, a golden value, or an assertion.
4. [`SETUP.md`](SETUP.md) — one-time self-hosted runner + branch protection setup.

## Running locally

```
pip install -r requirements.txt
python -m pytest -v
```

## Layout

- `harness/` — the shared wire-diff/DB/exe-invocation library (PLB-1243).
- `fixtures/` — the curated real-cause pool (`causes.json`) and per-flow golden values.
- `tests/` — one module per flow/ticket (PLB-1244–1248).

Nothing under `harness/`, `fixtures/`, or `tests/` exists yet beyond a placeholder — this repo
was set up for CI/PR workflow before the suite itself was written. See `PLAN.md` for build
order.
