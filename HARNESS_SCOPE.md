# Harness Scope — what's actually live today

This list is grounded in the real source tree (`I:\E_file_local\BatchFiling\_tyler_net4_extract`,
checked 2026-10-14), not in memory of what the cert-era build used to have. The rule: **the
harness only knows about an exe flag, table, or wire field if a currently-live flow actually
uses it.** Certification-era surface is listed at the bottom specifically so it's easy to
recognize and reject if it ever creeps back in.

## Exes the harness is allowed to call

Everything else in `_tyler_net4_extract` (`TaxLit13EfileSubmit.Net8` = ECF4, the cert-era exe)
is NOT called by the harness. ECF4 is a separate, much larger, cert-only surface — see
"Explicitly excluded" below.

| Exe | Flags the harness uses | Purpose |
|---|---|---|
| `TaxLit13PJSubmit.exe` | `--probe-causes`, `--filing-details`, `--preview-summary`, `--service-contacts`, `--attach-service-contact`, `--detach-service-contact`, `--sync-attorneys`, `--refresh-codes`, `--no-confirm`, bare `<serial>` | PJ subsequent filing + service contacts |
| `TaxLit13IntvSubmit.exe` | `--probe-causes`, `--filing-details`, `--preview-summary`, `--register-attorneys`, `--sync-attorneys`, `--refresh-codes`, `--dry-run`, `--no-confirm`, bare `<serial>` | Interventions subsequent filing |
| `TaxLit13LitSubmit.exe` | all of the above + `--existing-case`, `--count-pages`, `--dry-run` | Litigation new-case OP *and* existing-case judgment/dismissal/non-suit (one exe, flag selects the path) |
| `TaxLit13CalcFee.exe` | `--serial` | Fee calculation (multi-petition math) |
| `TaxLit13GetFilingDetails.exe` | `--serial` | **The official read-back tool** — this is what the wire-level layer uses to confirm Tyler actually echoes a value, not a side query |
| `TaxLit13GetCaseList.exe` | `--serial` | Case/filing list read, used by fixture-health probing |
| `TaxLit13SyncPartyTypes.exe` | `--location`, `--dry-run`, `--diag` | PICK_LIST party-type refresh, used by the SQL-level layer |

`--allow-unserved`, `--search-public-list`, `--try-bar` exist on these exes too but aren't
exercised by any of the four live flows today — leave them out unless a flow starts using one.

## Tables the harness is allowed to query

Found by grepping the three live submit exes directly: `TAXLIT0`, `TAXLIT13`, `TAXLIT13A`,
`TAXLIT13C`, `TAXLIT2`, `TAXLIT2A`, `TAXLIT3`, `CONTACT0`, `CONTACT3`, `CONTACT9`, `PICK_LIST`,
`COUNTERS`, `User_Profile`.

**`CallbackMessages` is referenced in the code but explicitly excluded from the harness.** It
doesn't exist in `LawBase_Design` (confirmed, PJ build finding 1) — Accepted/Rejected can never
arrive there. Any harness check that depends on a callback landing must be written to not run
in Design, not loosened to "pass anyway" (see `TESTING_RULES.md` rule 3).

## Wire fields the harness asserts on

Chosen because each one is a field that has *actually broken* in production history, not a
theoretical concern:

- `FilerTypeText` (the hardcode bug)
- `FilingAttorneyID` value **and** its category pairing (`IDENTIFICATION` vs `CASEPARTYATTORNEYID`)
- `Multiplier` on optional services, specifically at quantity 1
- `PersonGivenName` / `PersonSurName` / `PersonFullName` (the defendant name-split rule)
- Copies — Service calculation (`totalPages * defCount`)
- `eFile` vs `eFile and Serve` (service-contact presence toggle)
- `FilingDescription` (filing-level) vs per-file `BinaryDescriptionText`
- `DocumentFileControlID`
- cross-team `FilingTeam` guard (which team claimed/can claim a given TAXLIT13 row)

## Explicitly excluded — cert-era, not part of any live flow

- **ECF4's own CLI surface** (`TaxLit13EfileSubmit.exe` / `Program.cs`): `--dump-codes`,
  `--check-policy`, `--probe-codes`, `--check-parties`, `--service-history`,
  `--service-attached-cases`, `--get-user-btn`, `--auth-check`, `--auth-check-btn`,
  `--case-search-btn`, `--case-search`, `--get-case-btn`, `--load-case-btn`,
  `--get-filinglist-btn`, `--list-users`, `--get-user`, `--list-attorneys`,
  `--list-payment-accounts`, `--attach-envelope`, `--sync-firm-contacts`/`--sync-firm-list`.
  None of these are called by PJ/Interventions/Litigation. ECF4 itself is not one of this
  suite's four tested flows.
- **The EFSP certification workbook/checklist surface** (66 APIs, SF1-SF7, O3/O4, Appendix A/B
  mappings) — one-time Tyler cert artifact, not an ongoing regression concern.
- **Top-level cert-era trees**: `_efsp_cert/`, `_taxlit_pick_explore/`, `_wt_callback_design/`
  in the BatchFiling repo. Scratch/cert work, not the live simplified e-file tab.
- **ECF5** — a separate, still-in-progress migration with its own tooling rules
  ([[lawbase-ecf5-tooling-and-workflow]]). Not in scope here; give it its own suite later if
  wanted.
- **Clerk Doc Export** (`TaxLit13ExportClerkDocs(Design).exe`) — a separate workflow/ticket
  track, not one of PLB-1244 through 1247.
- **UI/screen automation** — never in scope, per the original plan.

If a future change makes one of these relevant again (e.g. ECF4 gets rebuilt with the
FilerType fix and goes back into real use), that's a deliberate, discussed scope change to
this file — not something to quietly start testing because the code happens to be nearby.
