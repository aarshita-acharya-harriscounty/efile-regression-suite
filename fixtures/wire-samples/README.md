Real outbound ReviewFiling envelopes captured on 2026-10-05, copied verbatim from
`Desktop\Efile\wire-20261005\`.

**These are PRE-FIX captures and are NOT golden "known-good" values.** They were taken
before the three 10/05 fixes landed, so they still contain the known bugs:

| File | Envelope | Known-bad content it still carries |
|---|---|---|
| `pj_328380.xml` | 328380 | `FilingAttorneyID` = firm id under category `CASEPARTYATTORNEYID` (the mismatched pair Tyler silently discards) |
| `intv_328381.xml` | 328381 | same mismatched attorney pair |
| `litex_328383.xml` | 328383 | same mismatched attorney pair |
| `litnew_328382.xml` | 328382 | defendant transmitted as `Maria` / `Assigns`, and no `PersonFullName` element at all |
| `intv_clean_328386.xml` | 328386 | first-intervention path on the clean case |

They exist for exactly one purpose: **verifying the extractors in `harness/wire.py` can
see what is actually in an envelope.** `tests/test_01_wire_extractors.py` asserts that the
extractors correctly surface these known defects — if a change ever makes those tests
report these files as clean, the extractor is broken, which is the failure mode that would
otherwise let a real regression pass silently.

Do not "update" these files to post-fix values. If you want golden known-good values, they
belong in a separate per-flow golden file captured from a verified-good envelope, with the
evidence recorded per `TESTING_RULES.md` rule 2.

## Post-fix captures

`pj_postfix_20261006.xml` is a different kind of file from the five above: it is a
**known-good** PJ envelope, captured after the three 2026-10-05 fixes and after PLB-1169's
e-service work landed, and it is the golden capture `tests/test_pj.py` diffs against
(`fixtures/golden/pj_subsequent.json` records the provenance and the evidence for every value).

Keeping both generations of PJ envelope is deliberate:
`test_the_prefix_capture_still_shows_the_bug_this_one_fixed` asserts that `pj_328380.xml` still
carries `CASEPARTYATTORNEYID` while this one carries `IDENTIFICATION`. A post-fix golden is only
worth having if the suite can demonstrably tell it apart from a pre-fix envelope.

It contains no email addresses — the envelope identifies service recipients purely by Tyler
contact GUID — so unlike the service-history fixtures it needed no redaction.
