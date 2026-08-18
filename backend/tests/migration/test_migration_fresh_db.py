from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
DB_URL = os.getenv("AGENTHUB_MIGRATION_TEST_DB_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="set AGENTHUB_MIGRATION_TEST_DB_URL to a real empty Postgres DB",
)


def _alembic(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"db_url={DB_URL}", *args],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )


def test_fresh_db_upgrade_head():
    result = _alembic("upgrade", "head")
    assert result.returncode == 0, result.stderr


def test_fresh_db_downgrade_upgrade():
    assert _alembic("downgrade", "0010").returncode == 0
    assert _alembic("upgrade", "head").returncode == 0
