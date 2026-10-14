# E-File Regression Suite — Testing Rules

These rules exist for one reason: a regression suite is only as trustworthy as the
discipline around *not* editing it to get a green run. Every rule below is tied to a real
incident from this project's history, not a generic best practice — follow the link if the
"why" isn't obviously enough to act on by itself.

**Core principle: a failing test is a signal to investigate, never an obstacle to clear.**

## Rule 1 — Never adjust an assertion or golden value without a primary source

Don't change an expected value because the real output "is probably fine" or "the test
environment must be off." Get the actual root cause confirmed by something authoritative:
Tyler's own echoed value, the Tyler portal, a real DB row, Tyler's EFSP Guide spec, or an
explicit statement from the user. "Plausible" is not a primary source.

*Why:* the FilerType hardcode bug sent the wrong code on every subsequent filing for the
entire length of this project. `ErrorCode=0` and a clean DB write both looked fine the whole
time — it was caught only by diffing the wire XML against the exe's own printed value. A
test that had been "fixed" to accept whatever FilerType came out would have hidden it
forever.

## Rule 2 — A fixture/golden-value change is its own commit

Never bundle a change to a golden file or the fixture pool into the same commit as a source
code fix. State the evidence (the Tyler echo, the portal screenshot, the user's ruling) in
that commit's message. A golden-value edit hidden inside a "fixed the bug" commit is exactly
how a test quietly gets weaker without anyone noticing in review.

## Rule 3 — Don't loosen a test to pass; mark known gaps explicitly instead

No silently turning an exact-match assertion into a substring/contains/not-null check,
catching an exception that used to legitimately fail the test, or deleting/commenting out a
failing case. If a flow has a real, accepted, not-yet-fixed bug (today: the mangled
defendant-name split, and the fact that Accepted/Rejected callbacks can never arrive in
Design), mark that specific case `xfail` with a ticket number **only after the user has
agreed it's an accepted gap** — never as a unilateral way to make a run go green.

## Rule 4 — Assert on content, never on exit code alone

`ErrorCode=0` has already hidden one invisible-for-the-project's-length bug (FilerType) and
the Multiplier-omitted-at-qty-1 bug only surfaced as error 129 once someone deliberately
exercised the branch. Every flow test must diff the actual outbound wire XML field-by-field
against its golden file *and* query the DB write-back — never just check that the exe
returned success or printed "Sent."

## Rule 5 — Fixtures can rot; report that distinctly from a real regression

Cause 202656147 lost all its party data on Tyler stage between sessions with no code change
on our side. `test_00_fixture_health.py` re-probes every pool cause before anything else
runs. A dead fixture must fail as *"FIXTURE UNHEALTHY: re-pick cause X"* — never silently
swapped for another cause, and never reported as if the flow logic itself regressed.

## Rule 6 — One fix, one commit, re-verify before moving on

When a run surfaces several failures, report all of them, but investigate and fix them one
at a time, each as its own commit with its own re-verification — not a batch of speculative
changes landed together. Carries over the existing git-discipline rule for this source tree.

## Rule 7 — Design only

This suite targets `LawBase_Design` and Tyler stage. Never Sandbox, never Prod, and never
write outside the approved fixture-pool causes or a fresh-case SEED script without asking
first.

## Rule 8 — When code and a written requirement disagree, present both and ask

Don't declare the code wrong on the strength of a meeting note or spec reading alone. On
2026-10-05 the code was correct and a meeting-note reading was wrong, twice, in the same
session, before the user settled it. If a test's expected behavior and a requirement
document disagree, show both readings and ask which one is right — don't pick one and edit
the test to match your own reading.

## Rule 9 — Tyler/the DB is the source of truth, not the test's prior expectation

If a test fails against real Tyler stage output and there's no primary-source evidence the
environment itself changed, treat the live response as correct and re-derive the test's
expectation from it — don't assume "the environment must be flaky" as a default excuse to
dismiss a failure.

## Rule 10 — Run the full suite on every change, no matter how small

A one-line edit is exactly how the Multiplier bug and the FilingAttorneyID category bug both
shipped — neither looked like it touched anything beyond the line being changed, and both
were in a shared file (`FilingReviewMessageInspector.cs`) that every one of the four flows
runs through. There is no such thing as a change too small to regress something else in this
codebase. Concretely:

- Every PR must run the full suite before it's mergeable — not just the test file that
  "obviously" covers the changed code. Partial/targeted runs are for your own local iteration
  only, never the signal that gates a merge.
- **Current enforcement mechanism (until `SETUP.md` section 1's self-hosted runner exists):**
  the committed `hooks/pre-push` hook, enabled via `git config core.hooksPath hooks`, runs the
  full suite and blocks the push on failure. This is not a weaker, temporary version of the
  rule — a push that skips it (`--no-verify`) is exactly as forbidden as merging a red CI
  check once CI exists. Once the runner is registered, CI becomes the actual merge gate and
  the hook becomes a second, redundant layer — not a replacement for CI, keep both.
- A PR/push cannot go through with a known failure, full stop — no "I'll fix it after,"
  no bypassing the hook, no merging with a check still pending.
- This applies to changes inside the suite itself too (a fixture, a golden file, a harness
  helper) — not just to the C# source being tested. A harness bug can hide a real regression
  just as effectively as a loosened assertion can (rule 3).
- If a change is so small you're tempted to skip the run, that is itself the signal to run it,
  not skip it — "it's just a one-liner" has already been wrong twice in this project's history.
