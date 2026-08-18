from __future__ import annotations

import re
from pathlib import Path

from app.models import Base

BACKEND = Path(__file__).resolve().parents[2]
VERSIONS = BACKEND / "alembic" / "versions"


def test_every_model_table_has_a_migration():
    created: set[str] = set()
    for path in VERSIONS.glob("*.py"):
        text = path.read_text()
        created.update(re.findall(r'op\.create_table\(\s*"([a-z_0-9]+)"', text))

    model_tables = set(Base.metadata.tables.keys())
    missing = sorted(model_tables - created)

    assert missing == [], f"model tables missing from migrations: {missing}"
