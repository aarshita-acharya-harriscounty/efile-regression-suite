"""Invokes the deployed exes exactly as a human would, and reads what they leave behind."""
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .config import FLOWS, TOOLS, WIRE_DUMP_NAME


@dataclass
class Run:
    returncode: int
    stdout: str
    stderr: str
    command: list

    @property
    def output(self):
        return self.stdout + self.stderr


def run_exe(exe: Path, args=(), timeout=600):
    if not exe.exists():
        raise FileNotFoundError(f"exe not deployed: {exe}")
    cmd = [str(exe), *[str(a) for a in args]]
    p = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, cwd=str(exe.parent)
    )
    return Run(p.returncode, p.stdout or "", p.stderr or "", cmd)


def run_flow(flow_key, args=(), timeout=600):
    flow = FLOWS[flow_key]
    return run_exe(flow.exe, [*args, *flow.extra_args], timeout=timeout)


def run_tool(tool_key, args=(), timeout=600):
    return run_exe(TOOLS[tool_key], args, timeout=timeout)


@dataclass
class ProbeResult:
    cause: str
    tracking_id: str = None
    case_party_id: str = None
    case_party_attorney_id: str = None
    court: str = None
    fileable: bool = False
    errors: list = field(default_factory=list)

    @property
    def summary(self):
        if self.fileable:
            return f"cause {self.cause}: fileable (court={self.court})"
        why = "; ".join(self.errors) or "missing party / attorney id"
        return f"cause {self.cause}: NOT fileable - {why}"


_NONE = {"(none)", "", "(null)"}


def _clean(v):
    v = (v or "").strip()
    return None if v in _NONE else v


def probe_causes(flow_key, causes, timeout=900):
    """Runs `--probe-causes <cause..>` and parses its per-cause block.

    Read-only against Tyler (CaseSearch + GetCase); submits nothing."""
    causes = [str(c) for c in causes]
    run = run_flow(flow_key, ["--probe-causes", *causes], timeout=timeout)

    results = {c: ProbeResult(cause=c) for c in causes}
    current = None
    for line in run.output.splitlines():
        s = line.strip()
        m = re.fullmatch(r"-{3}\s*(\d+)\s*-{3}", s)
        if m:
            current = results.get(m.group(1)) or ProbeResult(cause=m.group(1))
            results[m.group(1)] = current
            continue
        if current is None:
            continue
        if s.startswith("CaseTrackingID"):
            current.tracking_id = _clean(s.split("=", 1)[-1])
        elif s.startswith("CASEPARTYID"):
            current.case_party_id = _clean(s.split("=", 1)[-1])
        elif s.startswith("CASEPARTYATTORNEYID"):
            current.case_party_attorney_id = _clean(s.split("=", 1)[-1])
        elif s.startswith("case court"):
            current.court = _clean(s.split("=", 1)[-1])
        elif s.startswith("==> not fileable"):
            current.errors.append(s.removeprefix("==>").strip())
        elif s.startswith(("search failed:", "GetCase failed:")):
            current.errors.append(s)

    for r in results.values():
        r.fileable = bool(
            r.tracking_id and r.case_party_id and r.case_party_attorney_id and not r.errors
        )
    return results, run


def wire_dump_path(flow_key):
    return FLOWS[flow_key].dump_dir / WIRE_DUMP_NAME


def capture_wire(flow_key, dest_dir, label=None):
    """Copies the exe's outbound dump somewhere stable, immediately after a run.

    Required for PJ (shares ECF4's folder) and for the two Litigation flows (share one
    folder) - reading the dump later can hand you a different run's envelope."""
    src = wire_dump_path(flow_key)
    if not src.exists():
        raise FileNotFoundError(f"no wire dump at {src} - did the exe reach Tyler?")
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = dest_dir / f"{flow_key}_{label or stamp}.xml"
    shutil.copy2(src, dest)
    return dest


@dataclass
class ReportedContact:
    """One row of `--service-contacts` output, as the operator sees it."""

    attached: bool
    name: str
    firm: str = None
    email: str = None
    contact_id: str = None
    last_action: str = None


# Matches PjTools.ServiceContactsAsync's own formatting:
#   [ATTACHED] Angelica Hernandez  (hcao)
#              angelica.hernandez@lgbs.com
#              id=6dd420f2-...  last=Attach 2026-10-05 19:32:11Z
_CONTACT_HEAD_RE = re.compile(r"^\[(ATTACHED|detached)\]\s+(.*?)(?:\s{2}\((.*)\))?$")
_CONTACT_ID_RE = re.compile(r"^id=(\S+)\s+last=(\S+)")


def parse_service_contacts(output):
    """Parses `--service-contacts <cause>`; read-only, submits nothing, attaches nothing."""
    contacts = []
    current = None
    for line in output.splitlines():
        s = line.strip()
        head = _CONTACT_HEAD_RE.match(s)
        if head:
            current = ReportedContact(
                attached=head.group(1) == "ATTACHED",
                name=head.group(2).strip(),
                firm=(head.group(3) or "").strip() or None,
            )
            contacts.append(current)
            continue
        if current is None:
            continue
        ident = _CONTACT_ID_RE.match(s)
        if ident:
            current.contact_id = ident.group(1)
            current.last_action = ident.group(2)
        elif "@" in s and current.email is None:
            current.email = s
    return contacts


@dataclass
class PreviewSummary:
    """The confirmation screen `--preview-summary` prints, parsed.

    This is the real submit code path stopping one step short of sending, so what it shows is
    what a live send would have shown - but note it runs AFTER service-contact registration,
    so it is not purely read-only against Tyler. See the warning in HARNESS_SCOPE.md."""

    rows: dict = field(default_factory=dict)
    eserve: list = field(default_factory=list)
    mail_only: list = field(default_factory=list)
    unserved: list = field(default_factory=list)

    def row(self, key):
        return self.rows.get(key.lower())


_ROW_RE = re.compile(r"^([A-Za-z][A-Za-z ./-]*?):\s{1,}(.*)$")
_METHOD_RE = re.compile(r"^(.*?)\s{2}\((.*)\)$")


def parse_preview_summary(output):
    """Parses PjConfirmDialog.RenderText's layout: `  Key:<pad>value` rows, then the
    SERVICE (FROM THE CERTIFICATE OF SERVICE) section's three sub-lists."""
    summary = PreviewSummary()
    section = None
    pending = None
    for raw in output.splitlines():
        s = raw.strip()
        upper = s.upper()
        if upper.startswith("SERVICE (FROM THE CERTIFICATE OF SERVICE"):
            section = "service"
            continue
        # Section() underlines each heading with 76 dashes. That rule is not a heading and
        # must not close the section it just opened.
        if s and not s.strip("-"):
            continue
        if s and raw[:1] != " " and s == upper and ":" not in s and any(c.isalpha() for c in s):
            # Any other all-caps Section() heading closes the service section.
            section = None
        if s.startswith("Served by mail"):
            section = "mail"
            continue
        if s.startswith("*** CANNOT BE SERVED"):
            section = "unserved"
            continue
        if s.startswith("***"):
            continue

        row = _ROW_RE.match(s)
        if row and not s.startswith("e-serve"):
            summary.rows[row.group(1).strip().lower()] = row.group(2).strip()
            continue

        if section == "service":
            if s.startswith("e-serve"):
                pending = {"name": s[len("e-serve"):].strip(), "email": None,
                           "for": None, "source": None}
                summary.eserve.append(pending)
            elif pending is not None:
                if s.startswith("for:"):
                    pending["for"] = s[4:].strip()
                elif s.startswith("source:"):
                    pending["source"] = s[7:].strip()
                elif "@" in s and pending["email"] is None:
                    pending["email"] = s
        elif section in ("mail", "unserved"):
            m = _METHOD_RE.match(s)
            if m:
                entry = {"name": m.group(1).strip(), "method": m.group(2).strip()}
                (summary.mail_only if section == "mail" else summary.unserved).append(entry)
    return summary


ENVELOPE_RE = re.compile(r"envelope\D{0,12}(\d{5,8})", re.IGNORECASE)
ERRORCODE_RE = re.compile(r"ErrorCode\D{0,4}(-?\d+)", re.IGNORECASE)


def parse_envelope(output):
    m = ENVELOPE_RE.search(output)
    return m.group(1) if m else None


def parse_error_code(output):
    m = ERRORCODE_RE.search(output)
    return m.group(1) if m else None
