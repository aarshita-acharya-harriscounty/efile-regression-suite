"""The curated real-cause fixture pool (fixtures/causes.json)."""
import json
from dataclasses import dataclass
from functools import lru_cache

from .config import FIXTURE_DIR

POOL_FILE = FIXTURE_DIR / "causes.json"


@dataclass(frozen=True)
class CaseFixture:
    cause: str
    case_serial: int
    court: str
    active: bool
    flows: tuple
    filings: dict
    why: str
    last_verified: str

    def filing_serial(self, flow_key):
        return self.filings.get(flow_key)

    def __str__(self):
        return f"cause {self.cause} (case {self.case_serial})"


@lru_cache(maxsize=1)
def load_pool():
    data = json.loads(POOL_FILE.read_text(encoding="utf-8"))
    return tuple(
        CaseFixture(
            cause=str(e["cause"]),
            case_serial=e["case_serial"],
            court=e.get("court"),
            active=bool(e.get("active")),
            flows=tuple(e.get("flows", ())),
            filings={k: v for k, v in (e.get("filings") or {}).items()},
            why=e.get("why", ""),
            last_verified=e.get("last_verified", ""),
        )
        for e in data["pool"]
    )


def active_fixtures():
    return [f for f in load_pool() if f.active]


def retired_fixtures():
    return [f for f in load_pool() if not f.active]


def fixtures_for(flow_key):
    return [f for f in active_fixtures() if flow_key in f.flows]


def by_cause(cause):
    for f in load_pool():
        if f.cause == str(cause):
            return f
    raise KeyError(f"cause {cause} is not in the fixture pool")
