"""GET /eval/benchmark/latest 契约测试。"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes import eval as eval_routes
from app.config import settings


def test_benchmark_report_missing_returns_404(monkeypatch):
    monkeypatch.setattr(
        settings, "BENCHMARK_REPORT_PATH", "/nonexistent/evaluation_report.json"
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            eval_routes.latest_benchmark_report(
                user=SimpleNamespace(id=None, organization_id=None)
            )
        )
    assert exc.value.status_code == 404


def test_benchmark_report_returns_parsed_json(tmp_path, monkeypatch):
    report = tmp_path / "evaluation_report.json"
    report.write_text(
        json.dumps({"experiment": "P0-2_EVALUATION", "runs": 416}),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "BENCHMARK_REPORT_PATH", str(report))
    result = asyncio.run(
        eval_routes.latest_benchmark_report(
            user=SimpleNamespace(id=None, organization_id=None)
        )
    )
    assert result["runs"] == 416


def test_benchmark_report_corrupt_returns_500(tmp_path, monkeypatch):
    report = tmp_path / "evaluation_report.json"
    report.write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(settings, "BENCHMARK_REPORT_PATH", str(report))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            eval_routes.latest_benchmark_report(
                user=SimpleNamespace(id=None, organization_id=None)
            )
        )
    assert exc.value.status_code == 500
