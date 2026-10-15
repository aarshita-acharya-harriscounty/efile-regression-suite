Real `GetServiceInformationHistory` responses — Tyler's answer to "who is on this case's
service list, and is each of them currently attached?" (ECF4 cert operation O5, reached by
`TaxLit13PJSubmit.exe --service-contacts <cause>`).

| File | Case | Captured |
|---|---|---|
| `pj_202653957_20261006.xml` | cause 202653957 / CaseTrackingID `0ebc7976-…` | 2026-10-06 14:05 local, from `%LOCALAPPDATA%\TaxLit13EfileSubmit\last-service-info-history-raw.xml` |

These are **read-back responses, not golden "correct" values** — they record what Tyler held at
one moment. `tests/test_pj.py` uses this one to pin three behaviours of the response format
that a parser can plausibly get wrong while still looking like it works:

1. **"Currently attached" is decided by the latest TIMESTAMP**, not by element order. Perdue's
   entry here carries 3 Attach and 37 Detach actions and is attached.
2. **The actions come back newest-first in this capture**, which means a parser that takes
   element `[0]` is accidentally right and one that takes `[-1]` is confidently wrong — and
   neither is reading the timestamp. The test asserts the parser survives the list being
   reversed, so it cannot be passing for that accidental reason.
3. **One case-level detach fans out into many log entries.** A single
   `DetachServiceContact` call with no CasePartyID produced eighteen identical Detach rows at
   one timestamp, twice over. The row count in this log is *not* a call count.

It also happens to show that a firm registered as a service contact comes back split across
`PersonGivenName`/`PersonSurName` at the first comma (`Perdue,` / `Brandon, Fielder, Collins &
Mott, L.L.P.`), since Tyler stores every contact as a person.

## One redaction

This file is otherwise verbatim. A single personal address — stand-in test data someone put on
the pro-se defendant's Design row so the "party served at her own email" branch could be
exercised at all — was replaced with `redacted-pro-se-defendant@example.invalid` rather than
committing a personal email into this repo. Nothing the tests assert depends on it: that
contact is asserted by its Tyler `SERVICECONTACTID` and its resolution source, and the golden
file explains why its address is deliberately not pinned. The three real contacts
(professional/firm addresses on the certificate of service) are untouched.

If you would rather hold the byte-for-byte original, re-copy it from the path in the table
above and drop the redaction note — but then keep in mind what the file contains.
