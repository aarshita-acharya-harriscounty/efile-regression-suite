"""PLB-1248: SQL-level / PICK_LIST regression checks. No Tyler call, no exe invocation -
this whole file is read-only queries against LawBase_Design, and exists to catch the data
layer breaking before anyone gets as far as a Sandbox or Tyler-stage submission.

Grounded directly in the live source tree (I:\\E_file_local\\BatchFiling\\_tyler_net4_extract,
grepped 2026-10-14), not in memory of an older build: Design's PICK_LIST only ever holds
three 'Efile%' lists today (EfileAttorney, EfileLitExFilingCode, EfilePJDocSecurity) - the
~20-list cert-era shape documented in lawbase-efile-current-workflow.md belongs to Sandbox's
ECF4 build, which this suite deliberately does not target (HARNESS_SCOPE.md).

Two of the three (EfileLitExFilingCode, EfilePJDocSecurity) have NO write path in any live
exe - they are hand-seeded once and nothing refreshes them. A row-count drop on either is
permanent until a human notices, which is exactly the 'wiped out and nobody caught it' failure
mode this file exists to catch. EfileAttorney is the opposite case: TaxLit13PJSubmit.exe
--sync-attorneys (PjTools.SyncAttorneysAsync) rewrites it from Tyler's live firm roster on
every run, so its row count is expected to drift - the only thing worth asserting there is
that it's never driven to zero by something outside that sync path.
"""
import json

import pytest

from harness import db
from harness.config import FIXTURE_DIR

BASELINE = json.loads((FIXTURE_DIR / "picklist_baseline.json").read_text(encoding="utf-8"))
LISTS = {p["pick_name"]: p for p in BASELINE["picklists"]}
LIST_NAMES = sorted(LISTS)


@pytest.mark.db
def test_exactly_the_expected_efile_picklists_exist():
    """Catches a 4th Efile* list silently appearing (schema drift / an old cert-era list
    getting re-synced into Design) as readily as one of the 3 disappearing or getting
    renamed (a rename makes the old name vanish from this set just as a delete would)."""
    live = db.distinct_pick_name_prefixes("Efile%")
    assert live == set(LIST_NAMES), (
        f"Live Efile* picklists in LawBase_Design are {sorted(live)}, expected exactly "
        f"{LIST_NAMES} (fixtures/picklist_baseline.json) - something added, removed, or "
        f"renamed one"
    )


@pytest.mark.db
def test_pick_list_primary_key_is_still_name_and_value():
    """The whole suite's duplicate/truncation reasoning assumes PICK_LIST has a PK on
    (PICK_NAME, PICK_VALUE). If that constraint is ever dropped (e.g. during an unrelated
    schema change), silent duplicate rows become possible with no error at insert time."""
    assert db.pick_list_primary_key_columns() == ["PICK_NAME", "PICK_VALUE"]


@pytest.mark.db
@pytest.mark.parametrize("pick_name", LIST_NAMES)
def test_picklist_row_count_never_drops_below_its_floor(pick_name):
    spec = LISTS[pick_name]
    rows = db.pick_list(pick_name)
    assert len(rows) >= spec["min_rows"], (
        f"PICK_LIST('{pick_name}') has {len(rows)} row(s), expected at least "
        f"{spec['min_rows']} ({spec['maintained_by']}: {spec['sync_mechanism']}). "
        f"This is the 'wiped out' failure mode - see fixtures/picklist_baseline.json."
    )


@pytest.mark.db
@pytest.mark.parametrize("pick_name", LIST_NAMES)
def test_picklist_has_no_inactive_rows_hiding_a_soft_delete(pick_name):
    """None of the three sync/seed paths for these lists ever sets Inactive='Y' - as of
    2026-10-14 every row in all three is 'N'. A row flipping to inactive is the same
    practical outcome as a delete (it drops out of any WHERE Inactive='N' dropdown) and
    deserves the same attention, not a silent pass."""
    rows = db.pick_list(pick_name)
    inactive = [r["PICK_VALUE"] for r in rows if (r["Inactive"] or "").strip().upper() == "Y"]
    assert not inactive, (
        f"PICK_LIST('{pick_name}') has {len(inactive)} row(s) marked Inactive, which no "
        f"known sync path for this list does today: {inactive[:10]}"
    )


@pytest.mark.db
@pytest.mark.parametrize("pick_name", LIST_NAMES)
def test_no_duplicate_pick_value_within_list(pick_name):
    """Belt-and-suspenders on top of the PK test above - if the PK were ever dropped, this
    is the check that would actually notice duplicate data landing."""
    rows = db.pick_list(pick_name)
    values = [r["PICK_VALUE"] for r in rows]
    dupes = sorted({v for v in values if values.count(v) > 1})
    assert not dupes, f"PICK_LIST('{pick_name}') has duplicate PICK_VALUE rows: {dupes}"


PICK_VALUE_MARGIN_CASES = [
    pytest.param(
        "EfileLitExFilingCode",
        marks=pytest.mark.xfail(
            reason=(
                "PLB-1248: real Tyler filing code 'Counter Claim/Cross Action/Interpleader/"
                "Intervention/Third Party' is already 64 of 65 chars - accepted as a known "
                "gap 2026-10-14 (user sign-off) rather than widening PICK_LIST.PICK_VALUE in "
                "Design. gen_picklist_sql.ps1 (Desktop\\Efile\\Litigation) now skips-and-warns "
                "on any FUTURE value that actually exceeds 65, mirroring PjTools.cs's "
                "EfileAttorney guard, so this can no longer get worse silently - but today's "
                "64 is unchanged by that guard, which is why this still needs to stay xfail "
                "rather than passing for a wrong reason. Revisit if the column is ever widened."
            ),
            strict=True,
        ),
    ),
    "EfilePJDocSecurity",
    "EfileAttorney",
]


@pytest.mark.db
@pytest.mark.parametrize("pick_name", PICK_VALUE_MARGIN_CASES)
def test_pick_value_has_safety_margin_before_the_column_truncates_it(pick_name):
    """PICK_VALUE is varchar(65) in Design. PjTools.SyncAttorneysAsync already codes
    defensively against this for EfileAttorney (skips and logs any attorney name over 65
    chars rather than letting SQL truncate it silently into a dead, unmatchable row), and
    gen_picklist_sql.ps1 now does the same for EfileLitExFilingCode - but neither guard
    changes a value that's already close today, which is what this test actually measures.
    Warn well before the actual limit, not just at it: a value sitting at 64/65 today is one
    slightly-longer Tyler description away from a silent truncation that produces a
    PICK_VALUE nothing else can ever exact-match again."""
    width = db.column_width("PICK_LIST", "PICK_VALUE")
    margin = BASELINE["pick_value_width_warn_margin"]
    rows = db.pick_list(pick_name)
    longest = max((len(r["PICK_VALUE"] or "") for r in rows), default=0)
    assert longest <= width - margin, (
        f"PICK_LIST('{pick_name}')'s longest PICK_VALUE is {longest} chars against a "
        f"varchar({width}) column - within {width - longest} chars of silent truncation "
        f"(warn margin is {margin}). Widen the column or shorten the source value before "
        f"this actually truncates."
    )


@pytest.mark.db
def test_litexfilingcode_every_row_has_a_tyler_filingcatpk_id():
    """ExtraInfo1 is the numeric Tyler FilingCatPk id LitFilingRunner.cs needs to actually
    submit TaxLit13.FilingCode - a blank here means the row shows up in the dropdown but
    can never actually file."""
    rows = db.pick_list("EfileLitExFilingCode")
    blank = [r["PICK_VALUE"] for r in rows if not (r["ExtraInfo1"] or "").strip()]
    assert not blank, f"EfileLitExFilingCode rows with no ExtraInfo1 (Tyler id): {blank}"


@pytest.mark.db
def test_litexfilingcode_blank_fee_rows_match_the_known_set_exactly():
    """Two rows (Motion to Transfer, Notice of Appeal) already have a blank ExtraInfo2 fee
    as of 2026-10-14 - pre-existing, not asserted away. Exact-set match (not 'at most these
    two') so a THIRD code going blank is caught as a regression, and either of these two
    getting a real fee value going forward is noticed rather than silently accepted."""
    known = BASELINE["known_blank_extrainfo2_fee_codes"]
    rows = db.pick_list(known["pick_name"])
    blank = {
        r["PICK_VALUE"]
        for r in rows
        if not (r["ExtraInfo2"] or "").strip()
    }
    assert blank == set(known["codes"]), (
        f"{known['pick_name']} rows with a blank ExtraInfo2 fee are {sorted(blank)}, "
        f"expected exactly {known['codes']} (fixtures/picklist_baseline.json)"
    )


@pytest.mark.db
def test_pjdocsecurity_extrainfo_schema_tags_are_uniform():
    """Every EfilePJDocSecurity row carries the literal pair
    ExtraInfo1='TylerDocumentTypeName' / ExtraInfo2='EfileLocationPk' - these are column-role
    tags, not per-row data, and look exactly like noise someone could 'clean up' without
    realizing they're load-bearing. Verified uniform across all 99 rows 2026-10-14."""
    rows = db.pick_list("EfilePJDocSecurity")
    pairs = {(r["ExtraInfo1"], r["ExtraInfo2"]) for r in rows}
    assert pairs == {("TylerDocumentTypeName", "EfileLocationPk")}, (
        f"EfilePJDocSecurity's ExtraInfo1/ExtraInfo2 are no longer uniform: {pairs}"
    )


@pytest.mark.db
def test_efileattorney_every_row_has_a_parseable_cached_tyler_id():
    """ResolveAttorneyByPickValue (LitFilingRunner.cs and its PJ/Interventions equivalents)
    doesn't just check ExtraInfo4 is non-blank - it does
    tylerInfo.IndexOf("id=", OrdinalIgnoreCase) and silently returns a null TylerAttorneyId
    if that substring isn't found, exactly the 'field goes missing with no error' shape every
    real bug in this project has had (FilerType, Multiplier, FilingAttorneyID). A non-blank
    ExtraInfo4 that's missing 'id=' would pass a bare not-blank check and still silently fail
    downstream, so this asserts the actual substring the real resolver depends on, not merely
    that the column has something in it."""
    rows = db.pick_list("EfileAttorney")
    bad = [
        r["PICK_VALUE"]
        for r in rows
        if "id=" not in (r["ExtraInfo4"] or "").lower()
    ]
    assert not bad, (
        f"EfileAttorney rows whose ExtraInfo4 has no 'id=' substring (silently resolves to "
        f"no TylerAttorneyId, per LitFilingRunner.cs's ResolveAttorneyByPickValue): {bad}"
    )


@pytest.mark.db
def test_efileattorney_has_not_lost_most_of_its_roster_at_once():
    """The 'never zero' floor above only catches a complete wipe. --sync-attorneys is a MERGE
    that only ever adds/updates rows for attorneys Tyler currently returns - it never deletes,
    so a legitimate roster change should look like slow drift (one or two names changing
    between runs), not a cliff. A sudden large drop from the last verified-good count is a
    distinct, more realistic failure mode than hitting exactly zero, and is otherwise
    invisible to every other test in this file. This is a heuristic tripwire, not a precise
    bound - a real, intentional mass roster change should move picklist_baseline.json's
    baseline_rows (its own commit, per TESTING_RULES.md rule 2), not get this test loosened."""
    spec = LISTS["EfileAttorney"]
    rows = db.pick_list("EfileAttorney")
    floor = spec["baseline_rows"] * spec["max_drop_fraction_from_baseline"]
    assert len(rows) >= floor, (
        f"EfileAttorney has {len(rows)} row(s), down from a last-verified-good baseline of "
        f"{spec['baseline_rows']} - more than a "
        f"{int((1 - spec['max_drop_fraction_from_baseline']) * 100)}% drop. --sync-attorneys "
        f"never deletes rows, so a drop this size did not come from a normal Tyler sync - "
        f"investigate before assuming it's organic roster drift."
    )
