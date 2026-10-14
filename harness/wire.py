"""Outbound ReviewFiling XML: parse, extract the scoped fields, diff against golden.

Namespace-agnostic local-name matching throughout. Never match wire XML with string or
regex searching - a self-closing element reads as present-but-empty and has already
produced confidently wrong conclusions on this project.
"""
from lxml import etree


def load(path):
    return etree.parse(str(path))


def _all(doc, name):
    return doc.findall(f".//{{*}}{name}")


def _text(doc, name):
    els = _all(doc, name)
    return (els[0].text or "").strip() if els else None


def _texts(doc, name):
    return [(e.text or "").strip() for e in _all(doc, name)]


def _child_text(el, name):
    for ch in el:
        if etree.QName(ch).localname == name:
            return (ch.text or "").strip()
    return None


def filing_attorney(doc):
    els = _all(doc, "FilingAttorneyID")
    if not els:
        return None
    el = els[0]
    return {
        "id": _child_text(el, "IdentificationID"),
        "category": _child_text(el, "IdentificationCategoryText"),
    }


def person_names(doc):
    out = []
    for el in _all(doc, "PersonName"):
        out.append(
            {
                "given": _child_text(el, "PersonGivenName"),
                "surname": _child_text(el, "PersonSurName"),
                "full": _child_text(el, "PersonFullName"),
            }
        )
    return out


def optional_services(doc):
    out = []
    for el in _all(doc, "DocumentOptionalService"):
        out.append(
            {
                "code": _child_text(el, "IdentificationID"),
                "multiplier": _child_text(el, "Multiplier"),
            }
        )
    return out


def extract(doc):
    """Every field in HARNESS_SCOPE.md's wire list, plus the context needed to read them."""
    tracking = _text(doc, "CaseTrackingID")
    return {
        "filer_type": _text(doc, "FilerTypeText"),
        "filing_attorney": filing_attorney(doc),
        "filing_action": _text(doc, "FilingAction"),
        "filing_party_ids": [
            _child_text(e, "IdentificationID") for e in _all(doc, "FilingPartyID")
        ],
        "document_file_control_id": _text(doc, "DocumentFileControlID"),
        "filing_description": _text(doc, "DocumentDescriptionText"),
        "filing_code": _text(doc, "RegisterActionDescriptionText"),
        "file_descriptions": _texts(doc, "BinaryDescriptionText"),
        "attachment_count": len(_all(doc, "DocumentAttachment")),
        "optional_services": optional_services(doc),
        "person_names": person_names(doc),
        "case_tracking_id": tracking,
        "payment_amount": _text(doc, "Amount"),
        "case_category": _text(doc, "CaseCategoryText"),
        "case_type": _text(doc, "CaseTypeText"),
        "is_subsequent": bool(tracking),
    }


def extract_file(path):
    return extract(load(path))


def compare(actual, golden, path=""):
    """Returns a list of human-readable mismatches. Only keys present in `golden` are
    checked, so a golden file is an explicit allowlist of what this flow promises -
    adding a key tightens the test, never loosens it."""
    problems = []
    for key, want in golden.items():
        here = f"{path}.{key}" if path else key
        if key not in actual:
            problems.append(f"{here}: field not extracted at all (expected {want!r})")
            continue
        got = actual[key]
        if isinstance(want, dict) and isinstance(got, dict):
            problems += compare(got, want, here)
        elif isinstance(want, list) and isinstance(got, list):
            if len(want) != len(got):
                problems.append(f"{here}: expected {len(want)} item(s), got {len(got)}: {got!r}")
            else:
                for i, (w, g) in enumerate(zip(want, got)):
                    if isinstance(w, dict) and isinstance(g, dict):
                        problems += compare(g, w, f"{here}[{i}]")
                    elif w != g:
                        problems.append(f"{here}[{i}]: expected {w!r}, got {g!r}")
        elif want != got:
            problems.append(f"{here}: expected {want!r}, got {got!r}")
    return problems


def multipliers_present_for_every_service(doc):
    """Tyler rejects an optional service with no <Multiplier> (ErrorCode 129), which is
    what omitting it at quantity 1 used to do. Returns the offending service codes."""
    return [s["code"] for s in optional_services(doc) if not s["multiplier"]]
