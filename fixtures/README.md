`causes.json` (the curated real-cause pool) and per-flow golden-value files land here. See
`../PLAN.md`'s fixture-strategy section for the pool itself and `../TESTING_RULES.md` rules
1-2-5 before editing anything in this folder.

Layout:

- `causes.json` — the curated real-cause pool (see `../PLAN.md`).
- `picklist_baseline.json` — PLB-1248's row-count floors and required-field shapes.
- `golden/` — per-flow known-good values. One file per flow, each recording not just the
  expected values but *where each one came from*, per `TESTING_RULES.md` rule 1.
- `wire-samples/` — real outbound ReviewFiling envelopes. Mostly PRE-fix, kept to prove the
  extractors can see known defects; read that folder's README before adding or changing one.
- `service-history/` — real `GetServiceInformationHistory` responses (the case-level service
  attachment read-back).
