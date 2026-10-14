"""Verifies harness/wire.py can actually see what is in a real envelope.

Every expected value below was read out of the captured file itself, which is why these
captures are PRE-FIX: they still contain the 2026-10-05 bugs. The point is that the
extractors must SURFACE those bugs. If a change ever makes these files look clean, the
extractor is broken - and a broken extractor is exactly how a real regression passes
silently (TESTING_RULES.md rules 4 and 10).

Offline: no DB, no Tyler, no submissions.
"""
import pytest

from harness import wire
from harness.config import WIRE_SAMPLE_DIR

SAMPLES = {
    "pj_328380": WIRE_SAMPLE_DIR / "pj_328380.xml",
    "intv_328381": WIRE_SAMPLE_DIR / "intv_328381.xml",
    "intv_clean_328386": WIRE_SAMPLE_DIR / "intv_clean_328386.xml",
    "litex_328383": WIRE_SAMPLE_DIR / "litex_328383.xml",
    "litnew_328382": WIRE_SAMPLE_DIR / "litnew_328382.xml",
}

SUBSEQUENT = ["pj_328380", "intv_328381", "intv_clean_328386", "litex_328383"]


@pytest.fixture(scope="module")
def extracted():
    return {name: wire.extract_file(path) for name, path in SAMPLES.items()}


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_sample_file_is_present_and_parses(name):
    assert SAMPLES[name].exists(), f"missing capture {SAMPLES[name]}"
    assert wire.extract_file(SAMPLES[name])["filer_type"] is not None


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_filer_type_is_the_resolved_code_not_the_not_applicable_hardcode(name, extracted):
    """54323 is the resolved value. 40467 is 'Not Applicable' - the code that was silently
    sent on every filing until 2026-10-01."""
    filer = extracted[name]["filer_type"]
    assert filer == "54323", f"{name}: FilerTypeText = {filer!r}"
    assert filer != "40467", f"{name}: FilerTypeText is the 'Not Applicable' hardcode"


@pytest.mark.parametrize("name", SUBSEQUENT)
def test_extractor_surfaces_the_known_mismatched_attorney_pair(name, extracted):
    """These four pre-fix subsequent filings each carry a FIRM attorney id under category
    CASEPARTYATTORNEYID - the pair Tyler accepts with ErrorCode 0 and then discards. The
    extractor has to report both halves or the bug is invisible."""
    atty = extracted[name]["filing_attorney"]
    assert atty is not None, f"{name}: FilingAttorneyID not extracted at all"
    assert atty["id"], f"{name}: attorney id not extracted"
    assert atty["category"] == "CASEPARTYATTORNEYID", (
        f"{name}: expected the known pre-fix category CASEPARTYATTORNEYID, got "
        f"{atty['category']!r}. If this capture was replaced with a post-fix envelope, "
        f"that violates fixtures/wire-samples/README.md."
    )


def test_extractor_distinguishes_the_correct_new_case_attorney_category(extracted):
    """The new-case path got it right even pre-fix, and that contrast is what proved the
    subsequent-filing pairing was our bug rather than a Tyler read-back gap."""
    atty = extracted["litnew_328382"]["filing_attorney"]
    assert atty["category"] == "IDENTIFICATION"
    assert atty["id"] == "a0e95b3d-f913-4efc-ba06-cf420941ddc8"


def test_extractor_surfaces_the_mangled_defendant_name(extracted):
    """Defendant 'Maria Conception Willis All Unknown Heirs, Successors Or Assigns' went
    out as Maria / Assigns - first-token/last-token split. The sibling defendant kept the
    real family surname, which is the contrast that settled the fix."""
    names = extracted["litnew_328382"]["person_names"]
    pairs = [(n["given"], n["surname"]) for n in names]
    assert ("Maria", "Assigns") in pairs, (
        f"extractor no longer surfaces the known mangled name; got {pairs!r}"
    )
    assert ("Cynthia", "Willis") in pairs


def test_extractor_reports_personfullname_absent_in_pre_fix_captures(extracted):
    """PersonFullName was added by the 10/05 fix so the clerk still sees the full legal
    designation. Absent here - and the extractor must say so rather than return a blank
    that reads as 'present but empty'."""
    for name, data in extracted.items():
        for person in data["person_names"]:
            assert person["full"] is None, (
                f"{name}: PersonFullName present in a pre-fix capture ({person!r}) - "
                f"was this file replaced?"
            )


def test_optional_services_and_multipliers_are_extracted_as_pairs(extracted):
    """A service whose Multiplier is missing is ErrorCode 129. Extracting the code and the
    multiplier together is what makes that detectable."""
    services = extracted["litnew_328382"]["optional_services"]
    assert services == [
        {"code": "209598", "multiplier": "18"},
        {"code": "209644", "multiplier": "2"},
    ], f"got {services!r}"


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_no_capture_has_a_service_missing_its_multiplier(name):
    offenders = wire.multipliers_present_for_every_service(wire.load(SAMPLES[name]))
    assert not offenders, f"{name}: optional service(s) {offenders} have no Multiplier"


def test_subsequent_versus_new_case_is_detected_from_case_tracking_id(extracted):
    for name in SUBSEQUENT:
        assert extracted[name]["is_subsequent"] is True, f"{name} should be subsequent"
        assert extracted[name]["case_tracking_id"], f"{name} has no CaseTrackingID"
    assert extracted["litnew_328382"]["is_subsequent"] is False
    assert extracted["litnew_328382"]["case_tracking_id"] is None
    assert extracted["litnew_328382"]["case_category"] == "143172"


def test_first_intervention_sends_a_new_party_reference(extracted):
    """On the clean case Harris County was not yet a party, so the envelope declares
    NewParty1 rather than an existing CASEPARTYID guid. This is the path the shared-case
    run never exercised."""
    assert extracted["intv_clean_328386"]["filing_party_ids"] == ["NewParty1"]
    assert extracted["intv_328381"]["filing_party_ids"] == [
        "c2650326-99ce-442a-839f-f3d569b20d45"
    ]


def test_attachment_counts_and_descriptions_line_up(extracted):
    """Per-file BinaryDescriptionText is what the clerk sees next to each attachment; one
    per attachment, or a document silently lost its label."""
    for name, data in extracted.items():
        assert data["attachment_count"] == len(data["file_descriptions"]), (
            f"{name}: {data['attachment_count']} attachment(s) but "
            f"{len(data['file_descriptions'])} description(s)"
        )
    assert extracted["pj_328380"]["attachment_count"] == 7
    assert extracted["litnew_328382"]["file_descriptions"] == [
        "Harris County's Original Petition",
        "Citation",
        "Citation_2",
    ]


def test_filing_level_description_and_code_are_separate_fields(extracted):
    pj = extracted["pj_328380"]
    assert pj["filing_description"] == "Harris County's Petition for Withdrawal of Excess Proceeds"
    assert pj["filing_code"] == "136718"
    assert pj["document_file_control_id"] == "99999902-202653957"


def test_client_reference_uses_the_eight_digit_prefix(extracted):
    """PJ/Interventions/Litigation all use 99999902-; ECF4's seven-digit 9999902- is a
    separate open question and not what these flows send."""
    for name in ["pj_328380", "intv_328381", "intv_clean_328386", "litex_328383"]:
        ref = extracted[name]["document_file_control_id"]
        assert ref.startswith("99999902-"), f"{name}: clientRef {ref!r}"


class TestCompare:
    """The diff engine itself. A compare() that quietly returns no problems would make
    every flow test vacuous."""

    def test_identical_values_report_nothing(self):
        assert wire.compare({"a": "1"}, {"a": "1"}) == []

    def test_a_changed_value_is_reported(self):
        problems = wire.compare({"filer_type": "40467"}, {"filer_type": "54323"})
        assert len(problems) == 1 and "40467" in problems[0]

    def test_a_field_the_extractor_never_produced_is_reported(self):
        problems = wire.compare({}, {"filer_type": "54323"})
        assert problems and "not extracted" in problems[0]

    def test_nested_dict_mismatch_is_reported_with_a_path(self):
        problems = wire.compare(
            {"filing_attorney": {"id": "x", "category": "CASEPARTYATTORNEYID"}},
            {"filing_attorney": {"id": "x", "category": "IDENTIFICATION"}},
        )
        assert len(problems) == 1
        assert "filing_attorney.category" in problems[0]

    def test_list_length_difference_is_reported(self):
        problems = wire.compare({"s": [{"code": "1"}]}, {"s": [{"code": "1"}, {"code": "2"}]})
        assert problems and "expected 2 item(s)" in problems[0]

    def test_list_element_mismatch_is_reported_with_an_index(self):
        problems = wire.compare(
            {"optional_services": [{"code": "209598", "multiplier": None}]},
            {"optional_services": [{"code": "209598", "multiplier": "1"}]},
        )
        assert len(problems) == 1 and "optional_services[0].multiplier" in problems[0]

    def test_golden_only_checks_keys_it_declares(self):
        """Extra extracted fields are not failures - a golden file is an allowlist, so
        adding a key tightens coverage and can never loosen it."""
        assert wire.compare({"a": "1", "b": "2"}, {"a": "1"}) == []
