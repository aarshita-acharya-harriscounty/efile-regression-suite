"""Single place for every environment fact the suite depends on."""
import os
from dataclasses import dataclass, field
from pathlib import Path

SQL_SERVER = "SVTUSLAWBASESQL"
SQL_DATABASE = "LawBase_Design"
ODBC_DRIVER = "ODBC Driver 17 for SQL Server"

CONNECTION_STRING = (
    f"DRIVER={{{ODBC_DRIVER}}};SERVER={SQL_SERVER};DATABASE={SQL_DATABASE};"
    "Trusted_Connection=yes;TrustServerCertificate=yes"
)

EFILING_ROOT = Path(r"L:\Modules\EFiling")
REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "fixtures"
WIRE_SAMPLE_DIR = FIXTURE_DIR / "wire-samples"

_LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA", ""))
WIRE_DUMP_NAME = "last-reviewfiling-outbound.xml"


@dataclass(frozen=True)
class Flow:
    key: str
    exe: Path
    dump_dir: Path
    team: str
    extra_args: tuple = ()
    # PJ writes to ECF4's folder because it links the shared tyler-net4 inspector rather
    # than forking it. A PJ capture can therefore be an ECF4 run's output and vice versa -
    # always stamp/copy a PJ dump immediately after the run, never read it later.
    shared_dump: bool = False


FLOWS = {
    "pj": Flow(
        key="pj",
        exe=EFILING_ROOT / "PJ" / "TaxLit13PJSubmit.exe",
        dump_dir=_LOCALAPPDATA / "TaxLit13EfileSubmit",
        team="PJ",
        shared_dump=True,
    ),
    "interventions": Flow(
        key="interventions",
        exe=EFILING_ROOT / "Interventions" / "TaxLit13IntvSubmit.exe",
        dump_dir=_LOCALAPPDATA / "TaxLit13IntvSubmit",
        team="Interventions",
    ),
    "litigation_op": Flow(
        key="litigation_op",
        exe=EFILING_ROOT / "Litigation" / "TaxLit13LitSubmit.exe",
        dump_dir=_LOCALAPPDATA / "TaxLit13LitSubmit",
        team="Litigation",
    ),
    # Same exe as litigation_op; --existing-case selects the subsequent-filing path, and
    # the two necessarily share one dump path.
    "litigation_existing": Flow(
        key="litigation_existing",
        exe=EFILING_ROOT / "Litigation" / "TaxLit13LitSubmit.exe",
        dump_dir=_LOCALAPPDATA / "TaxLit13LitSubmit",
        team="LitExisting",
        extra_args=("--existing-case",),
    ),
}

# PJ's read-only query tools dump into their OWN folder, unlike the submit path, which writes
# its outbound envelope into ECF4's (see Flow.shared_dump above).
PJ_TOOL_DUMP_DIR = _LOCALAPPDATA / "TaxLit13PJSubmit"

TOOLS = {
    "calcfee": EFILING_ROOT / "TaxLit13CalcFee.exe",
    "filing_details": EFILING_ROOT / "TaxLit13GetFilingDetails.exe",
    "case_list": EFILING_ROOT / "TaxLit13GetCaseList.exe",
}

# Flows whose test needs a case that already carries a Sent filing.
SUBSEQUENT_FLOWS = ("pj", "interventions", "litigation_existing")
