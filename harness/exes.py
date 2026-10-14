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


ENVELOPE_RE = re.compile(r"envelope\D{0,12}(\d{5,8})", re.IGNORECASE)
ERRORCODE_RE = re.compile(r"ErrorCode\D{0,4}(-?\d+)", re.IGNORECASE)


def parse_envelope(output):
    m = ENVELOPE_RE.search(output)
    return m.group(1) if m else None


def parse_error_code(output):
    m = ERRORCODE_RE.search(output)
    return m.group(1) if m else None
