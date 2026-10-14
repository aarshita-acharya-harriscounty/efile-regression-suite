import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import pool  # noqa: E402


def pytest_report_header(config):
    from harness.config import SQL_DATABASE, SQL_SERVER

    active = ", ".join(f.cause for f in pool.active_fixtures())
    return [f"target: {SQL_SERVER}/{SQL_DATABASE} (Tyler stage)", f"active fixture causes: {active}"]


@pytest.fixture(scope="session")
def active_fixtures():
    return pool.active_fixtures()
