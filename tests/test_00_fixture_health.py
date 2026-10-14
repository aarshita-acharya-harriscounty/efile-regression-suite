"""Runs before every flow test. A dead fixture must be reported AS a dead fixture, not
mistaken for a flow regression - cause 202656147 rotted on Tyler stage between sessions
with no code change on our side, and that is the failure mode this file exists to name.
"""
import pytest

from harness import db, exes, pool
from harness.config import FLOWS, SUBSEQUENT_FLOWS, TOOLS

ACTIVE = pool.active_fixtures()
ACTIVE_IDS = [f.cause for f in ACTIVE]


def test_pool_file_has_active_fixtures():
    assert ACTIVE, "fixtures/causes.json has no active fixture - nothing can be tested"


@pytest.mark.parametrize("flow_key", sorted(FLOWS))
def test_flow_exe_is_deployed(flow_key):
    exe = FLOWS[flow_key].exe
    assert exe.exists(), f"{flow_key}: exe not deployed at {exe}"


@pytest.mark.parametrize("tool_key", sorted(TOOLS))
def test_tool_exe_is_deployed(tool_key):
    exe = TOOLS[tool_key]
    assert exe.exists(), f"{tool_key}: exe not deployed at {exe}"


@pytest.mark.parametrize("flow_key", sorted(FLOWS))
def test_every_flow_has_at_least_one_fixture(flow_key):
    assert pool.fixtures_for(flow_key), (
        f"{flow_key}: no active fixture covers this flow - its tests would silently "
        f"have nothing to run against"
    )


@pytest.mark.db
def test_database_is_reachable():
    row = db.one("SELECT DB_NAME() AS db")
    assert row["db"] == "LawBase_Design", f"connected to {row['db']}, expected LawBase_Design"


@pytest.mark.db
@pytest.mark.parametrize("fx", ACTIVE, ids=ACTIVE_IDS)
def test_fixture_cause_resolves_to_its_recorded_case(fx):
    case = db.case_by_cause(fx.cause)
    assert case is not None, (
        f"FIXTURE UNHEALTHY: cause {fx.cause} no longer exists in LawBase_Design.TAXLIT0 - "
        f"re-pick it and update fixtures/causes.json (TESTING_RULES.md rule 5)"
    )
    assert case["Serial"] == fx.case_serial, (
        f"FIXTURE UNHEALTHY: cause {fx.cause} now maps to CaseSerial {case['Serial']}, "
        f"but causes.json records {fx.case_serial}"
    )


@pytest.mark.db
@pytest.mark.parametrize("fx", ACTIVE, ids=ACTIVE_IDS)
def test_fixture_declares_a_filing_row_for_each_flow_it_claims(fx):
    missing = [f for f in fx.flows if fx.filing_serial(f) is None]
    assert not missing, (
        f"{fx}: claims flows {missing} but causes.json lists no TAXLIT13 serial for them"
    )


@pytest.mark.db
@pytest.mark.parametrize("fx", ACTIVE, ids=ACTIVE_IDS)
def test_declared_filing_rows_exist_and_belong_to_this_case(fx):
    for flow_key, serial in fx.filings.items():
        row = db.filing(serial)
        assert row is not None, (
            f"FIXTURE UNHEALTHY: {fx} {flow_key} -> TAXLIT13 serial {serial} does not exist"
        )
        assert row["CaseSerial"] == fx.case_serial, (
            f"FIXTURE UNHEALTHY: TAXLIT13 {serial} ({flow_key}) now hangs off case "
            f"{row['CaseSerial']}, not {fx.case_serial}"
        )


@pytest.mark.db
@pytest.mark.parametrize("fx", ACTIVE, ids=ACTIVE_IDS)
def test_declared_filing_rows_carry_the_expected_team(fx):
    for flow_key, serial in fx.filings.items():
        row = db.filing(serial)
        expected = FLOWS[flow_key].team
        assert row["FilingTeam"] == expected, (
            f"{fx} {flow_key}: TAXLIT13 {serial} has FilingTeam "
            f"{row['FilingTeam']!r}, expected {expected!r} - the cross-team guard would "
            f"refuse this row"
        )


@pytest.mark.db
@pytest.mark.parametrize("fx", ACTIVE, ids=ACTIVE_IDS)
def test_subsequent_flows_have_a_case_that_already_filed(fx):
    """A subsequent filing needs the case to already carry a Sent envelope. This is the
    precondition the whole pool strategy rests on, so it is checked, not assumed."""
    claimed = [f for f in fx.flows if f in SUBSEQUENT_FLOWS]
    if not claimed:
        pytest.skip(f"{fx} claims no subsequent-filing flow")
    sent = [
        r
        for r in db.filings_for_case(fx.case_serial)
        if (r["FilingStatus"] or "").strip() == "Sent" and r["EnvelopeNum"]
    ]
    assert sent, (
        f"FIXTURE UNHEALTHY: {fx} claims subsequent flows {claimed} but has no Sent "
        f"TAXLIT13 row with an envelope - there is nothing for a subsequent filing to "
        f"attach to"
    )


@pytest.mark.db
def test_retired_fixtures_are_documented_not_merely_deleted():
    for fx in pool.retired_fixtures():
        assert fx.why.strip(), (
            f"cause {fx.cause} is inactive with no 'why' - a retired fixture must record "
            f"why it was retired (TESTING_RULES.md rule 5)"
        )


@pytest.mark.db
def test_design_still_lacks_the_tables_the_scope_doc_excludes():
    """HARNESS_SCOPE.md excludes TAXLIT13E and EfileUserAuthSession because Design does not
    have them. If that changes, the exclusion needs re-deciding rather than silently
    staying stale."""
    for table in ("TAXLIT13E", "EfileUserAuthSession"):
        assert not db.table_exists(table), (
            f"{table} now EXISTS in LawBase_Design - HARNESS_SCOPE.md excludes it on the "
            f"grounds that it does not. Re-read that decision."
        )


@pytest.mark.db
def test_servebys_that_reach_the_citation_service_branches_are_still_set():
    """The Constable / Secretary-of-State citation branches are reachable in Design only
    because two TAXLIT2A rows were given ServeBy values by hand. If someone reverts them,
    those branches go untested and nothing else would say so."""
    fx = pool.by_cause("202653957")
    values = {
        r["TaxLit2ASerial"]: (r["ServeBy"] or "").strip()
        for r in db.serve_by_values(fx.case_serial)
    }
    assert values.get(131142) == "Constable", (
        f"TAXLIT2A 131142 ServeBy is {values.get(131142)!r}, expected 'Constable' - "
        f"re-apply Desktop\\Efile\\12_RESET_AND_ServeBy_Test.sql part 2"
    )
    assert values.get(131115) == "TxSecretaryState", (
        f"TAXLIT2A 131115 ServeBy is {values.get(131115)!r}, expected 'TxSecretaryState'"
    )


@pytest.mark.db
@pytest.mark.tyler
@pytest.mark.parametrize("fx", ACTIVE, ids=ACTIVE_IDS)
def test_tyler_can_still_see_the_fixture_case(fx):
    """The check that would have caught 202656147 rotting. Read-only: CaseSearch + GetCase,
    submits nothing."""
    results, run = exes.probe_causes("pj", [fx.cause])
    result = results[fx.cause]
    assert result.tracking_id, (
        f"FIXTURE UNHEALTHY: Tyler has no CaseTrackingID for cause {fx.cause}. "
        f"{result.summary}\n--- exe output ---\n{run.output[-1500:]}"
    )
    assert result.fileable, f"FIXTURE UNHEALTHY: {result.summary}"


@pytest.mark.db
@pytest.mark.tyler
@pytest.mark.parametrize("fx", [f for f in ACTIVE if f.court], ids=[f.cause for f in ACTIVE if f.court])
def test_fixture_court_matches_what_tyler_reports(fx):
    results, _ = exes.probe_causes("pj", [fx.cause])
    got = results[fx.cause].court
    assert got == fx.court, (
        f"{fx}: Tyler now reports court {got!r}, causes.json records {fx.court!r} - the "
        f"case may have been transferred; confirm before editing the fixture"
    )
