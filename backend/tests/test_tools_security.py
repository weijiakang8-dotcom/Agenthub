from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.engine import tools


async def run_query(sql: str) -> dict:
    return await tools.query_db.ainvoke({"sql": sql})


@pytest.mark.parametrize(
    "sql",
    [
        "update agents set name='x'",
        "select * from agents; drop table agents",
        "delete from agents",
    ],
)
def test_query_db_rejects_unsafe_or_multi_statement(sql):
    result = asyncio.run(run_query(sql))

    assert result["status"] == "failed"
    assert "Only a single read-only SELECT is allowed" in result["error"]


def test_query_db_executes_safe_select(monkeypatch):
    class FakeConnection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def execute(self, _statement):
            return SimpleNamespace(
                fetchall=lambda: [
                    SimpleNamespace(_mapping={"id": 1, "name": "research"})
                ]
            )

    monkeypatch.setattr(
        tools,
        "engine",
        SimpleNamespace(connect=lambda: FakeConnection()),
    )

    result = asyncio.run(run_query("select id, name from agents"))

    assert result == {
        "status": "success",
        "data": [{"id": 1, "name": "research"}],
        "error": None,
    }
