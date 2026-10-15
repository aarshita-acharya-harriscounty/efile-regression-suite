"""Tyler's GetServiceInformationHistory response: who is on a case's service list, and
whether they are currently attached.

Mirrors `PjTools.GetCaseServiceContactsAsync` deliberately, because the rule it implements is
not obvious and getting it wrong reads as a pass:

**"Currently attached" means the action with the LATEST TIMESTAMP is an Attach** - not the
first `<Action>` in document order, and not the last. A real response interleaves repeated
attach/detach cycles per recipient, and in the 2026-10-06 capture the actions happen to come
back newest-first, so a parser that took element [0] would be accidentally right and a parser
that took element [-1] would be confidently wrong. Neither is reading the timestamp, which is
the only thing that actually decides it.

Also note what a single case-level `DetachServiceContact` call looks like here: Tyler fans it
out across the case's party associations, so ONE call can land as eighteen identical Detach
entries at the same timestamp. The row count in this log is not a call count.
"""
from dataclasses import dataclass, field
from datetime import datetime

from lxml import etree


def _localname(el):
    return etree.QName(el).localname


def _first_text(el, name):
    for node in el.iter():
        if _localname(node) == name:
            text = (node.text or "").strip()
            if text:
                return text
    return None


def _parse_timestamp(text):
    if not text:
        return None
    # Tyler sends "2026-10-05T19:32:11.0Z". Python's fromisoformat handles the fractional
    # second but not the trailing Z before 3.11, and we want an aware datetime either way.
    cleaned = text.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


@dataclass
class ContactAction:
    action: str
    at: datetime = None


@dataclass
class ServiceContact:
    service_contact_id: str = None
    firm: str = None
    given: str = None
    surname: str = None
    email: str = None
    actions: list = field(default_factory=list)

    @property
    def name(self):
        return " ".join(p for p in (self.given, self.surname) if p)

    @property
    def last_action(self):
        """The action with the greatest timestamp. Actions with no parsable timestamp are
        ignored rather than treated as 'now' - an unparsable date must not be able to flip a
        contact's attached state."""
        dated = [a for a in self.actions if a.at is not None]
        if not dated:
            return self.actions[0] if self.actions else None
        return max(dated, key=lambda a: a.at)

    @property
    def is_attached(self):
        last = self.last_action
        return bool(last and (last.action or "").strip().lower() == "attach")

    def count(self, action):
        return sum(1 for a in self.actions if (a.action or "").strip().lower() == action.lower())


def parse(path):
    doc = etree.parse(str(path))
    contacts = []
    for recipient in doc.findall(".//{*}ServiceRecipient"):
        sc = ServiceContact()
        for ident in recipient.iter():
            if _localname(ident) != "IdentificationCategoryText":
                continue
            category = (ident.text or "").strip().upper()
            parent = ident.getparent()
            value = None
            for sibling in parent:
                if _localname(sibling) == "IdentificationID":
                    value = (sibling.text or "").strip()
                    break
            if category == "SERVICECONTACTID":
                sc.service_contact_id = value
            elif category == "FIRMNAME":
                sc.firm = value

        sc.given = _first_text(recipient, "PersonGivenName")
        sc.surname = _first_text(recipient, "PersonSurName")
        sc.email = _first_text(recipient, "ContactEmailID")

        for action_el in recipient.findall(".//{*}Action"):
            sc.actions.append(
                ContactAction(
                    action=_first_text(action_el, "ContactAction"),
                    at=_parse_timestamp(_first_text(action_el, "DateTime")),
                )
            )

        if sc.service_contact_id:
            contacts.append(sc)
    return contacts


def case_tracking_id(path):
    doc = etree.parse(str(path))
    els = doc.findall(".//{*}CaseTrackingID")
    return (els[0].text or "").strip() if els else None


def attached(contacts):
    return [c for c in contacts if c.is_attached]


def by_id(contacts, service_contact_id):
    for c in contacts:
        if c.service_contact_id == service_contact_id:
            return c
    return None
