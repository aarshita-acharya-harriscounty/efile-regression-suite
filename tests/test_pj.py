"""PLB-1244: regression coverage for the PJ (Post Judgement) e-file flow.

PJ has no separate initial-filing path - every PJ filing is a subsequent filing onto a case
that already exists in the Harris District Clerk's docket. So this file covers one flow in
two halves, which is how the ticket is written:

  1. the subsequent-filing wire contract (FilerTypeText, FilingAttorneyID + its category, the
     fixed PJ constants, the eight-digit client reference, the per-file descriptions)
  2. e-service / the Certificate of Service (PLB-1169): who gets served, resolved through
     TAXLIT2.AttyofRec -> Contact9 rather than the party's own firm row, and the fact that
     adding is the only operation this flow performs

PLAN.md's three assertion layers map onto markers here:

  (unmarked)    offline - the committed captures and the golden file. No DB, no Tyler.
  @db           read-only queries against LawBase_Design.
  @tyler        read-only live Tyler stage calls (--service-contacts, --filing-details).
  @tyler_write  runs the real submit path up to the point of sending. NOT read-only - see
                test_preview_summary_shows_the_certificate_of_service_split. Deselected by
                default.
  @submits      files a real envelope on Tyler stage. Deselected by default.

The ticket listed one open question - "whether runs are self-contained (new case -> subsequent
each run) or use a persistent already-filed fixture case" - and noted it was leaning
self-contained "to avoid fragile shared Sandbox state". That question was settled when PLAN.md
was agreed, in the other direction and for a reason the ticket's wording predates: this suite
does not target Sandbox at all (TESTING_RULES.md rule 7), and a persistent Design fixture
carrying an already-Sent TAXLIT13 row is exactly the precondition a subsequent-filing test
needs, with no setup. Fixture rot is handled as its own distinct failure
(test_00_fixture_health.py) rather than avoided by rebuilding state per run.
"""
import json
import re

import pytest

from harness import db, exes, pool, service_history, wire
from harness.config import FIXTURE_DIR, PJ_TOOL_DUMP_DIR, WIRE_SAMPLE_DIR

GOLDEN = json.loads((FIXTURE_DIR / "golden" / "pj_subsequent.json").read_text(encoding="utf-8"))
CAPTURE = FIXTURE_DIR / GOLDEN["capture"]
HISTORY_CAPTURE = FIXTURE_DIR / GOLDEN["service"]["history_capture"]
PREFIX_CAPTURE = WIRE_SAMPLE_DIR / "pj_328380.xml"

REQUIRED_CONTACTS = GOLDEN["service"]["required_contacts"]
MUST_NOT_SERVE = GOLDEN["service"]["must_not_be_eserved"]
FIXTURE = pool.by_cause(GOLDEN["cause"])
FILING_SERIAL = GOLDEN["filing_serial"]


@pytest.fixture(scope="module")
def envelope():
    return wire.extract_file(CAPTURE)


@pytest.fixture(scope="module")
def history():
    return service_history.parse(HISTORY_CAPTURE)


@pytest.fixture(scope="module")
def cos():
    return db.cos_rows(GOLDEN["case_serial"])


def _cos_row(rows, serial):
    for r in rows:
        if r["Serial"] == serial:
            return r
    raise AssertionError(f"COS row {serial} is gone from case {GOLDEN['case_serial']}")


# --------------------------------------------------------------------------------------
# Layer 1 - the subsequent-filing wire contract (offline)
# --------------------------------------------------------------------------------------


def test_capture_is_present_and_is_the_pj_flow(envelope):
    """PJ writes its outbound dump into ECF4's folder (config.Flow.shared_dump), so a file
    found there is only a PJ envelope if its PJ constants say so. Checked here rather than
    assumed, because every other assertion in this file rests on it."""
    assert CAPTURE.exists(), f"missing capture {CAPTURE}"
    assert envelope["filing_code"] == "136718"
    assert envelope["filing_description"] == "Harris County's Petition for Withdrawal of Excess Proceeds"
    assert envelope["document_file_control_id"] == f"99999902-{GOLDEN['cause']}"
    assert envelope["attachment_count"] == 7


def test_capture_matches_golden_wire_values(envelope):
    """The central assertion of this ticket. compare() treats the golden dict as an
    allowlist, so every key it declares is checked exactly and extra extracted fields are
    not failures - adding a key tightens this test and can never loosen it."""
    problems = wire.compare(envelope, GOLDEN["wire"])
    assert not problems, "PJ envelope no longer matches its golden values:\n  " + "\n  ".join(problems)


def test_filer_type_is_the_resolved_government_filer_code(envelope):
    """40467 is 'Not Applicable'. It was sent on every subsequent filing from the start of
    this project until 2026-10-01, with ErrorCode 0 and a clean DB write the whole time."""
    assert envelope["filer_type"] == "54323"
    assert envelope["filer_type"] != "40467", "the 'Not Applicable' FilerType hardcode is back"


def test_filing_attorney_is_susan_fuertes_paired_with_identification(envelope):
    """Both halves matter and they broke independently.

    The ID half: PJ used to send GetCase's CASEPARTYATTORNEYID, i.e. the first attorney on the
    case with no firm filtering - very possibly opposing counsel named as our filing attorney.

    The CATEGORY half: the id was then paired with category CASEPARTYATTORNEYID, which wants a
    case-party GUID, not a firm attorney id. Tyler accepted that envelope with ErrorCode 0 and
    silently discarded the field, so nothing short of the wire or the portal showed it."""
    atty = envelope["filing_attorney"]
    assert atty["id"] == "22b3f700-10c7-4558-af58-d74419c47e65"
    assert atty["category"] == "IDENTIFICATION", (
        f"FilingAttorneyID category is {atty['category']!r}. CASEPARTYATTORNEYID paired with a "
        f"firm attorney id is the pairing Tyler accepts and then throws away."
    )


def test_the_prefix_capture_still_shows_the_bug_this_one_fixed():
    """A post-fix golden is only meaningful if the suite can tell it from a pre-fix envelope.
    Both captures are PJ, on the same case; the attorney category is the difference."""
    before = wire.extract_file(PREFIX_CAPTURE)["filing_attorney"]
    after = wire.extract_file(CAPTURE)["filing_attorney"]
    assert before["category"] == "CASEPARTYATTORNEYID"
    assert after["category"] == "IDENTIFICATION"
    assert before["id"] == after["id"], (
        "the two captures should differ in the CATEGORY only - the firm attorney id was "
        "already correct before the 10/05 fix"
    )


@pytest.mark.db
def test_filing_description_is_the_pj_constant_not_the_grid_description(envelope):
    """LawBaseFilingSmokeTest.ReadyDoc.DocDescrName is overloaded, and TAXLIT13 has its own
    FilingDescription column that operators type into freely - on Serial 34 it currently reads
    '4BTN test - PJ excess proceeds packet'. The filing-level description on the wire is a
    fixed constant and must not track that column, or a test note ends up on the record."""
    row = db.filing(FILING_SERIAL)
    assert envelope["filing_description"] == GOLDEN["wire"]["filing_description"]
    assert envelope["filing_description"] != (row["FilingDescription"] or ""), (
        "the wire's filing description now equals TAXLIT13.FilingDescription - the grid column "
        "has been wired to the filing-level description"
    )


def test_every_attachment_has_its_own_file_description(envelope):
    """Per-file BinaryDescriptionText is what the clerk sees next to each attachment. One per
    attachment, or a document has silently lost its label."""
    assert envelope["attachment_count"] == len(envelope["file_descriptions"])
    assert envelope["file_descriptions"][0] == "Motion for Withdrawal of Excess Proceeds"
    assert all(d.strip() for d in envelope["file_descriptions"]), "a blank file description"


def test_client_reference_uses_the_eight_digit_prefix(envelope):
    """PJ's spec is 99999902- (eight digits). ECF4 builds 9999902- (seven); whether that is a
    real ECF4 bug is still open, but it is not what this flow sends."""
    ref = envelope["document_file_control_id"]
    assert ref.startswith("99999902-")
    assert not ref.startswith("9999902-")


def test_subsequent_filing_carries_tracking_id_and_omits_new_case_fields(envelope):
    """CaseCategoryText/CaseTypeText are new-case fields. Their presence on a subsequent
    filing would mean the flow had started building the wrong kind of envelope."""
    assert envelope["is_subsequent"] is True
    assert envelope["case_tracking_id"] == GOLDEN["wire"]["case_tracking_id"]
    assert envelope["case_category"] is None
    assert envelope["case_type"] is None


def test_pj_declares_no_parties(envelope):
    """PJ files onto a case that already has its parties. Declaring one would re-add a party
    that is already on the record - the failure mode SubsequentFiling.DeclareNewParty causes
    when COS parties leak into the Plaintiffs/Defendants bags."""
    assert envelope["person_names"] == []


def test_no_optional_service_is_missing_its_multiplier():
    """PJ requests no optional services today, so this is a tripwire rather than a check of
    current behaviour: omitting <Multiplier> at quantity 1 is ErrorCode 129, and that bug sat
    latent in all three runners until the constable branch was finally exercised."""
    offenders = wire.multipliers_present_for_every_service(wire.load(CAPTURE))
    assert not offenders, f"optional service(s) {offenders} carry no Multiplier"


# --------------------------------------------------------------------------------------
# Layer 2 - e-service: the envelope's serve list (offline)
# --------------------------------------------------------------------------------------


def test_every_envelope_service_contact_is_a_servicecontactid(envelope):
    contacts = envelope["service_contacts"]
    assert contacts, "the envelope declares no service contacts at all"
    for c in contacts:
        assert c["category"] == "SERVICECONTACTID", f"unexpected category {c['category']!r}"
        assert c["id"], "a service contact with an empty id"


def test_envelope_service_contact_ids_are_unique(envelope):
    """A duplicated recipient is the shape a double-add bug takes - and 'add-only' semantics
    make it the most likely way this flow could misbehave without erroring."""
    ids = [c["id"] for c in envelope["service_contacts"]]
    assert len(ids) == len(set(ids)), f"duplicate service contact id in {ids}"


@pytest.mark.parametrize("contact", REQUIRED_CONTACTS, ids=[c["name"] for c in REQUIRED_CONTACTS])
def test_required_cos_contact_is_in_the_envelope(contact, envelope):
    """Each of these is derivable from the case's COS by PjCosServiceContacts' own rule. The
    golden file records why each one is there; between them they cover all three resolution
    sources (attorney of record, firm fallback, party's own email)."""
    ids = {c["id"] for c in envelope["service_contacts"]}
    assert contact["service_contact_id"] in ids, (
        f"{contact['name']} ({contact['source']}) is on the Certificate of Service but has no "
        f"service contact in the envelope. Present ids: {sorted(ids)}"
    )


def test_mail_only_cos_party_gets_no_service_contact(envelope, history):
    """The other half of the serve rule: being on the COS is not the same as being e-served.
    A party whose only method is USPS Regular must not acquire a service contact - doing so
    would e-serve someone the certificate says was mailed."""
    served_emails = {
        (service_history.by_id(history, c["id"]).email or "").lower()
        for c in envelope["service_contacts"]
        if service_history.by_id(history, c["id"])
    }
    for party in MUST_NOT_SERVE:
        surname = party["name"].split()[0].lower()
        assert not any(surname in e for e in served_emails), (
            f"{party['name']} is mail-only ({party['method']}) but looks e-served"
        )
    # And the stronger structural form: no contact in the envelope is unaccounted for.
    for c in envelope["service_contacts"]:
        assert service_history.by_id(history, c["id"]) is not None, (
            f"envelope contact {c['id']} does not appear in the case's service history at all"
        )


def test_filing_action_is_efile_and_serve_when_contacts_resolved(envelope):
    """'Always eFile and Serve' and 'service contacts are Phase 2' are mutually exclusive -
    Tyler rejects an eFile-and-Serve envelope with no recipient (ErrorCode 283). PJ settles
    the action AFTER registration, on the list that actually resolved, so this pair must stay
    consistent: contacts present <-> EFileAndServe."""
    assert envelope["service_contacts"]
    assert envelope["filing_action"] == "EFileAndServe"


# --------------------------------------------------------------------------------------
# Layer 2b - e-service: the case-level attachment history (offline)
# --------------------------------------------------------------------------------------


def test_history_capture_parses_and_belongs_to_this_case(history):
    assert HISTORY_CAPTURE.exists()
    assert service_history.case_tracking_id(HISTORY_CAPTURE) == GOLDEN["service"]["case_tracking_id"]
    assert len(history) == 4
    for c in history:
        assert c.service_contact_id
        assert c.firm == "hcao", f"{c.name}: firm came back as {c.firm!r}"


def test_attached_state_is_decided_by_the_latest_timestamp(history):
    """'Currently attached' means the action with the greatest timestamp is an Attach - not
    the first action in document order and not the last. Perdue's history here is the proof
    case: it holds 3 Attach entries and 37 Detach entries, and is attached."""
    perdue = service_history.by_id(history, "2a3b8c23-a6a3-4ece-9e94-d994cddd6d76")
    assert perdue is not None
    assert perdue.count("Attach") > 1 and perdue.count("Detach") > 1, (
        "this assertion is only meaningful on a recipient with a mixed history"
    )
    assert perdue.is_attached
    assert perdue.last_action.action == "Attach"
    assert perdue.last_action.at == max(a.at for a in perdue.actions if a.at)


def test_a_naive_positional_read_of_the_history_would_be_wrong(history):
    """Why the timestamp rule is written out rather than left implicit: in this real response
    the actions come back newest-first, so taking element [0] is accidentally right while
    taking element [-1] is confidently wrong. Neither is reading the timestamp. If Tyler ever
    reverses the order, the parser must not care - this test documents that it does not."""
    perdue = service_history.by_id(history, "2a3b8c23-a6a3-4ece-9e94-d994cddd6d76")
    dated = [a for a in perdue.actions if a.at]
    assert dated[0].at == max(a.at for a in dated), "capture is no longer newest-first"
    assert dated[-1].action == "Attach" and dated[-1].at == min(a.at for a in dated)
    # The oldest entry is also an Attach, which is exactly how a [-1] reader gets the right
    # answer for the wrong reason. Reversed, the parser must still say attached.
    perdue.actions.reverse()
    assert perdue.is_attached
    perdue.actions.reverse()


def test_one_case_level_detach_fans_out_across_party_associations(history):
    """A single DetachServiceContact call with no CasePartyID produced eighteen identical
    Detach entries at one timestamp. The log's row count is not a call count - read it as
    state, never as an audit of how many calls were made."""
    perdue = service_history.by_id(history, "2a3b8c23-a6a3-4ece-9e94-d994cddd6d76")
    by_timestamp = {}
    for a in perdue.actions:
        if a.action == "Detach" and a.at:
            by_timestamp.setdefault(a.at, 0)
            by_timestamp[a.at] += 1
    assert max(by_timestamp.values()) >= 18, (
        f"expected a fan-out of 18+ Detach entries at one timestamp, got {by_timestamp}"
    )


@pytest.mark.parametrize("contact", REQUIRED_CONTACTS, ids=[c["name"] for c in REQUIRED_CONTACTS])
def test_required_contact_is_currently_attached_add_only(contact, history):
    """PLB-1169's scoping answer: add-only is sufficient, and detaching is deliberately not
    something this flow does (it changes what other firms see and generates real notification
    emails). So every contact this flow has ever added should still be attached."""
    found = service_history.by_id(history, contact["service_contact_id"])
    assert found is not None, f"{contact['name']} is not in the case's service history"
    assert found.is_attached, (
        f"{contact['name']} latest action is {found.last_action.action!r} at "
        f"{found.last_action.at} - this flow never detaches, so something else did"
    )


def test_a_firm_comes_back_split_across_the_person_name_fields(history):
    """Tyler stores every service contact as a person. A firm registered as one comes back
    with its name hacked across PersonGivenName/PersonSurName at the first comma, so the
    'name' it reports is not a clean organisation name. Recorded because any display or
    matching logic built on these fields has to expect it."""
    perdue = service_history.by_id(history, "2a3b8c23-a6a3-4ece-9e94-d994cddd6d76")
    assert perdue.given == "Perdue,"
    assert perdue.surname == "Brandon, Fielder, Collins & Mott, L.L.P."


# --------------------------------------------------------------------------------------
# Layer 3 - the COS resolution in LawBase_Design
# --------------------------------------------------------------------------------------


@pytest.mark.db
def test_cos_roster_for_the_fixture_case_is_intact(cos):
    """The COS is the input to everything in layer 2. If these rows change, the e-service
    assertions above are testing something else - so this fails as a fixture problem."""
    assert len(cos) == 4, (
        f"FIXTURE UNHEALTHY: case {GOLDEN['case_serial']} now has {len(cos)} COS rows, "
        f"expected 4: {[r['PartyName'] for r in cos]}"
    )
    serials = {r["Serial"] for r in cos}
    expected = {c["cos_taxlit2_serial"] for c in REQUIRED_CONTACTS} | {
        p["cos_taxlit2_serial"] for p in MUST_NOT_SERVE
    }
    assert serials == expected, f"COS row serials are {sorted(serials)}, expected {sorted(expected)}"


@pytest.mark.db
def test_attorney_of_record_resolves_through_contact9_not_the_firm_row(cos):
    """The load-bearing finding of PLB-1169, and the single most important assertion in the
    service half of this ticket.

    The COS row is a FIRM (Linebarger). TAXLIT2.AttyofRec points at a Contact9 row - that
    firm's roster entry for the individual attorney - and it is that person's address that
    belongs on the certificate. The firm's own CONTACT0 row carries a different, also-valid,
    also-lgbs.com address, which is what makes a regression here so quiet: reading the wrong
    one still yields a plausible address, ErrorCode 0 and a clean DB write."""
    row = _cos_row(cos, 101851)
    atty = next(c for c in REQUIRED_CONTACTS if c["cos_taxlit2_serial"] == 101851)

    assert row["AttyC9Serial"] == 496
    assert (row["AttyFirst"], row["AttyLast"]) == ("Angelica", "Hernandez")
    assert row["AttyEmail"] == atty["email"] == "angelica.hernandez@lgbs.com"
    assert row["PartyEmail"] == "houlitigation@lgbs.com", (
        "the firm row's own email changed - if it ever equals the attorney's, this test stops "
        "being able to tell the two sources apart and needs a new fixture"
    )
    assert row["AttyEmail"] != row["PartyEmail"], (
        "attorney-of-record and firm addresses are now identical; this case can no longer "
        "prove which one the resolver used"
    )


@pytest.mark.db
def test_attyofrec_points_at_the_contact9_linktype(cos):
    """LawBase link strings are '<linktype>^<serial>'. 100037 is Contact9 (people); 100000 is
    CONTACT0 (firms/parties). An AttyofRec that started pointing at 100000 would resolve to a
    firm and quietly lose every individual attorney name on the certificate."""
    row = _cos_row(cos, 101851)
    assert row["AttyofRec"] == "100037^496"
    link = db.contact9(496)["LinkSerial"]
    assert link == "100037^496", f"Contact9 496's own LinkSerial is {link!r}"


@pytest.mark.db
def test_cos_row_with_no_attorney_falls_back_to_the_firm_email(cos):
    """The contrast that makes the test above meaningful: an empty AttyofRec means there is no
    Contact9 person to prefer, and the firm's own address is then correctly what gets served."""
    row = _cos_row(cos, 101852)
    assert not (row["AttyofRec"] or "").strip(), "Perdue now has an attorney of record"
    assert row["AttyC9Serial"] is None
    assert row["PartyEmail"] == "PBFCM-Houston@pbfcm.com"


@pytest.mark.db
def test_cos_membership_is_the_checkbox_alone_not_a_role_rule():
    """The HotDocs computation this rule came from used to include the Atty-Plaintiff role as
    well, and was changed to checkbox-only on 2023-09-08. So a role-based rule must not creep
    back: this case has an Atty-in-Charge row with CertofService='N' that has to stay off the
    COS even though its role matches the Atty-* pattern the old rule used."""
    rows = db.taxlit2_rows(GOLDEN["case_serial"])
    atty_in_charge = [r for r in rows if (r["LitRole"] or "") == "Atty-in-Charge"]
    assert atty_in_charge, "FIXTURE UNHEALTHY: the Atty-in-Charge row this test needs is gone"
    for r in atty_in_charge:
        assert (r["CertOfService"] or "").strip() != "Y"

    cos_serials = {r["Serial"] for r in db.cos_rows(GOLDEN["case_serial"])}
    for r in atty_in_charge:
        assert r["Serial"] not in cos_serials, (
            f"{r['PartyName']} ({r['LitRole']}, CertofService="
            f"{r['CertOfService']!r}) is on the COS - a role-based rule is back"
        )


@pytest.mark.db
def test_serve_cert_is_multivalued_so_email_must_be_a_contains_test():
    """ServeCert holds things like 'Email, USPS Regular' and 'Email, USPS CMRRR, USPS
    Regular'. Any equality check against 'Email' silently drops those parties from e-service
    while the certificate still names them as served. This asserts the compound values really
    are present in Design, so the rule is being tested against the real shape of the data."""
    values = db.distinct_serve_cert_values()
    assert values, "no ServeCert values in Design at all"
    compound = [
        v["ServeCert"]
        for v in values
        if "," in v["ServeCert"] and "email" in v["ServeCert"].lower()
    ]
    assert compound, (
        f"no multi-valued Email ServeCert left in Design, so the 'contains' rule is no longer "
        f"being exercised by real data. Values present: {[v['ServeCert'] for v in values]}"
    )
    for value in compound:
        assert value != "Email"
        assert "email" in value.lower()


@pytest.mark.db
def test_the_mail_only_party_is_not_email_servable(cos):
    row = _cos_row(cos, 101849)
    methods = row["ServiceMethods"] or ""
    assert methods == "USPS Regular"
    assert "email" not in methods.lower() and "e-service" not in methods.lower()
    assert not (row["PartyEmail"] or "").strip()
    assert row["AttyC9Serial"] is None


@pytest.mark.db
def test_filing_attorney_picklist_row_holds_the_id_the_wire_sends(envelope):
    """Ties the DB layer to the wire layer. PJ resolves its fixed attorney name through
    PICK_LIST('EfileAttorney'), parsing the Tyler id out of the ExtraInfo4 text - so a sync
    that rewrote that row with a different id would change the filing attorney on the wire
    with nothing else to show for it."""
    rows = [r for r in db.pick_list("EfileAttorney") if r["PICK_VALUE"] == "Susan Fuertes"]
    assert len(rows) == 1, "PICK_LIST('EfileAttorney') has no single 'Susan Fuertes' row"
    extra = rows[0]["ExtraInfo4"] or ""
    match = re.search(r"id=([0-9a-fA-F-]{36})", extra)
    assert match, f"no 'id=<guid>' in ExtraInfo4: {extra!r}"
    assert match.group(1) == envelope["filing_attorney"]["id"]


@pytest.mark.db
def test_pj_filing_row_wrote_back_what_it_sent():
    """PLAN.md's third layer. ErrorCode 0 has already hidden one project-length bug, so the
    DB side of a send is checked too."""
    row = db.filing(FILING_SERIAL)
    expected = GOLDEN["db_writeback"]
    assert row is not None, f"TAXLIT13 {FILING_SERIAL} is gone"
    assert row["FilingTeam"] == expected["filing_team"]
    assert (row["FilingStatus"] or "").strip() == expected["filing_status"]
    assert row["clientRefNum"] == expected["client_ref_num"]
    assert not (row["LastError"] or "").strip(), f"LastError: {row['LastError']!r}"
    assert db.document_count(FILING_SERIAL) == expected["document_count"]
    # Deliberately not pinned to a value: every new live send legitimately replaces it.
    assert row["EnvelopeNum"], "no EnvelopeNum - this row has never been sent"
    assert str(row["EnvelopeNum"]).isdigit()


@pytest.mark.db
def test_the_second_pj_fixture_is_the_no_service_contact_control():
    """Cause 202310045 is PJ's other pool fixture and has ZERO COS rows, which makes it the
    control for the eFile/eFile-and-Serve toggle: a PJ filing there must go out as plain
    eFile. Recorded as a test because 'this case has no COS data' is a precondition, not a
    coincidence - if someone adds COS rows to it, that control is gone."""
    other = pool.by_cause("202310045")
    assert db.cos_rows(other.case_serial) == [], (
        f"cause {other.cause} has acquired COS rows - it was the only no-service-contact PJ "
        f"fixture, so the eFile-only branch now has nothing covering it"
    )
    row = db.filing(other.filing_serial("pj"))
    assert row["FilingTeam"] == "PJ"


# --------------------------------------------------------------------------------------
# Layer 4 - live Tyler read-back (read-only)
# --------------------------------------------------------------------------------------


@pytest.mark.db
@pytest.mark.tyler
def test_service_contacts_readback_reports_the_required_contacts_attached():
    """The live form of the add-only guarantee, via GetServiceInformationHistory. Read-only:
    --service-contacts attaches nothing and detaches nothing."""
    run = exes.run_flow("pj", ["--service-contacts", GOLDEN["cause"]], timeout=900)
    contacts = exes.parse_service_contacts(run.output)
    assert contacts, (
        f"--service-contacts parsed no rows. Tyler may hold none, or the output format "
        f"changed.\n--- output ---\n{run.output[-2000:]}"
    )
    by_id = {c.contact_id: c for c in contacts}
    for required in REQUIRED_CONTACTS:
        found = by_id.get(required["service_contact_id"])
        assert found is not None, (
            f"{required['name']} ({required['service_contact_id']}) is not in Tyler's service "
            f"history for this case. Reported: {sorted(by_id)}"
        )
        assert found.attached, f"{required['name']} is in the history but detached"


@pytest.mark.db
@pytest.mark.tyler
def test_tyler_echoes_the_filing_attorney_back():
    """The read-back that settled the attorney bug. Tyler returns FilingAttorneyID only when
    it accepted the id/category pairing - it came back empty on every subsequent filing while
    the mismatched pair was being sent. A non-empty echo matching Susan's id is therefore
    direct evidence from Tyler that the 10/05 fix is still in force.

    Queried by FILINGID, deliberately. GetFilingDetails by ENVELOPEID returns an envelope
    summary that contains no FilingAttorneyID element at all - so querying that way produces
    exactly the same empty result the BUG produced, for an entirely unrelated reason. That is
    a trap worth naming: the two are indistinguishable from the assertion's point of view."""
    filing_id = db.filing_id(FILING_SERIAL)
    assert filing_id, (
        f"TAXLIT13A has no TylerTrakingID for filing {FILING_SERIAL} - nothing to query by"
    )
    run = exes.run_flow(
        "pj", ["--filing-details", filing_id, FIXTURE.court, "FILINGID"], timeout=900
    )
    dump = PJ_TOOL_DUMP_DIR / "last-filingdetails.xml"
    assert dump.exists(), (
        f"no filing-details dump at {dump}\n--- output ---\n{run.output[-2000:]}"
    )
    echoed = wire.filing_attorney(wire.load_dotnet_dump(dump))
    assert echoed and echoed["id"], (
        f"Tyler echoed no FilingAttorneyID for FILINGID {filing_id} - which is exactly how "
        f"the mismatched-pair bug looked. Category sent: "
        f"{GOLDEN['wire']['filing_attorney']['category']}"
    )
    assert echoed["id"] == GOLDEN["wire"]["filing_attorney"]["id"]


# --------------------------------------------------------------------------------------
# Layer 5 - the real submit path, stopping short of sending (NOT read-only)
# --------------------------------------------------------------------------------------


@pytest.mark.db
@pytest.mark.tyler
@pytest.mark.tyler_write
def test_preview_summary_shows_the_certificate_of_service_split():
    """Runs the real submit code path and stops one step before sending, so the review screen
    it prints is the one a live send would show - the operator check that replaces ticking
    boxes in Tyler's portal.

    NOT READ-ONLY, which is why this carries @tyler_write and is deselected by default:
    PartyServiceContactRegistrar.EnsureRegisteredAsync runs BEFORE the --preview-summary
    return (PjFilingRunner.cs lines 410 and 864, same method), so a COS party who is not yet
    registered gets created in Tyler's firm service-contact list by this call. On this fixture
    all three e-servable parties are already registered, so it reuses rather than creates -
    but that is a property of the data, not a guarantee of the flag."""
    run = exes.run_flow("pj", ["--preview-summary", str(FILING_SERIAL)], timeout=900)
    summary = exes.parse_preview_summary(run.output)
    assert "stopping here, nothing was sent" in run.output, (
        f"--preview-summary did not stop before sending\n--- output ---\n{run.output[-3000:]}"
    )

    assert summary.row("Filing action") == "eFile and Serve"
    assert summary.row("Filing attorney")
    assert "Susan Fuertes" in summary.row("Filing attorney")
    assert summary.row("Reference number") == f"99999902-{GOLDEN['cause']}"

    served = {(r["email"] or "").lower() for r in summary.eserve}
    for required in REQUIRED_CONTACTS:
        if required["email"]:
            assert required["email"].lower() in served, (
                f"{required['name']} is missing from the review screen's e-serve list. "
                f"Listed: {sorted(served)}"
            )
    hernandez = next(
        (r for r in summary.eserve if "angelica.hernandez" in (r["email"] or "").lower()), None
    )
    assert hernandez is not None
    assert "attorney" in (hernandez["source"] or "").lower(), (
        f"Hernandez's source reads {hernandez['source']!r} - the review screen should say she "
        f"came from the attorney-of-record chain, not the firm row"
    )

    mail_names = " ".join(m["name"] for m in summary.mail_only).lower()
    for party in MUST_NOT_SERVE:
        assert party["name"].split()[0].lower() in mail_names, (
            f"{party['name']} is not in the 'served by mail' list: {summary.mail_only}"
        )

    assert summary.unserved == [], (
        f"the CANNOT BE SERVED block is populated: {summary.unserved}. On this fixture every "
        f"COS party is resolvable, and an unserved party BLOCKS the send."
    )


# --------------------------------------------------------------------------------------
# Layer 6 - a real envelope on Tyler stage
# --------------------------------------------------------------------------------------


@pytest.mark.db
@pytest.mark.tyler
@pytest.mark.submits
def test_live_submit_matches_golden_and_writes_back(tmp_path):
    """The full three-layer check against a freshly sent envelope. Deselected by default:
    this files a real envelope on Tyler stage, so it runs only when someone asks for it
    explicitly (`pytest -m submits`).

    NOT YET EXECUTED - written as part of PLB-1244 but never run, pending sign-off on filing
    live envelopes from the suite. Treat its first run as unproven code.

    Captures the dump IMMEDIATELY after the run: PJ shares ECF4's dump folder, so reading it
    later can hand you a different run's envelope entirely."""
    before = db.filing(FILING_SERIAL)
    run = exes.run_flow("pj", [str(FILING_SERIAL), "--no-confirm"], timeout=1800)
    captured = exes.capture_wire("pj", tmp_path, label="live")

    error_code = exes.parse_error_code(run.output)
    assert error_code == "0", (
        f"ErrorCode {error_code}\n--- output ---\n{run.output[-3000:]}"
    )

    problems = wire.compare(wire.extract_file(captured), GOLDEN["wire"])
    assert not problems, "live envelope differs from golden:\n  " + "\n  ".join(problems)

    after = db.filing(FILING_SERIAL)
    assert (after["FilingStatus"] or "").strip() == "Sent"
    assert not (after["LastError"] or "").strip(), f"LastError: {after['LastError']!r}"
    assert after["EnvelopeNum"] and after["EnvelopeNum"] != before["EnvelopeNum"], (
        "EnvelopeNum did not change - the row was not written back for this send"
    )
