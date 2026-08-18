"""独立真实外部数据服务（仅用于 Phase 4.1 本地真实验证）。"""

from __future__ import annotations

import json
import time
import urllib.request

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title="external-test-service")

_OPS: dict[str, dict] = {}
_IDEM: dict[str, str] = {}
_PENDING: dict[str, str] = {}


@app.get("/api/external/data")
def external_data(query: str = Query(...), delay_ms: int = 0, status: int = 200):
    if delay_ms:
        time.sleep(delay_ms / 1000)
    if status != 200:
        return JSONResponse(
            status_code=status,
            content={"status": "error", "error": f"injected-{status}"},
        )
    return {
        "status": "success",
        "data": [
            {
                "id": "external-001",
                "query": query,
                "value": "real external test value",
            }
        ],
    }


class EffectRequest(BaseModel):
    operation_id: str
    idempotency_key: str
    mode: str = "success"
    delay_ms: int = 0


@app.post("/api/external/effect")
def external_effect(request: EffectRequest):
    if request.idempotency_key in _IDEM:
        existing_id = _IDEM[request.idempotency_key]
        existing = _OPS[existing_id]
        return {
            "operation_id": existing_id,
            "committed": existing["committed"],
            "status": "duplicate",
            "execution_count": existing["execution_count"],
        }

    if request.mode == "timeout_committed":
        _OPS[request.operation_id] = {"committed": True, "execution_count": 1}
        _IDEM[request.idempotency_key] = request.operation_id
        if request.delay_ms:
            time.sleep(request.delay_ms / 1000)
        return {
            "operation_id": request.operation_id,
            "committed": True,
            "status": "committed",
            "execution_count": 1,
        }

    if request.mode == "timeout_not_committed":
        if request.idempotency_key in _PENDING:
            operation_id = _PENDING.pop(request.idempotency_key)
            _OPS[operation_id] = {"committed": True, "execution_count": 1}
            _IDEM[request.idempotency_key] = operation_id
            return {
                "operation_id": operation_id,
                "committed": True,
                "status": "committed",
                "execution_count": 1,
            }
        _OPS[request.operation_id] = {"committed": False, "execution_count": 0}
        _PENDING[request.idempotency_key] = request.operation_id
        if request.delay_ms:
            time.sleep(request.delay_ms / 1000)
        return {
            "operation_id": request.operation_id,
            "committed": False,
            "status": "not_committed",
            "execution_count": 0,
        }

    if request.mode == "unknown":
        _OPS[request.operation_id] = {"committed": None, "execution_count": 0}
        return JSONResponse(
            status_code=202,
            content={
                "operation_id": request.operation_id,
                "committed": None,
                "status": "unknown",
                "execution_count": 0,
            },
        )

    _OPS[request.operation_id] = {"committed": True, "execution_count": 1}
    _IDEM[request.idempotency_key] = request.operation_id
    return {
        "operation_id": request.operation_id,
        "committed": True,
        "status": "committed",
        "execution_count": 1,
    }


@app.get("/api/external/effect/{operation_id}")
def get_effect(operation_id: str):
    op = _OPS.get(operation_id)
    if op is None:
        return JSONResponse(status_code=404, content={"error": "not found"})
    return {
        "operation_id": operation_id,
        "committed": op["committed"],
        "status": (
            "unknown"
            if op["committed"] is None
            else ("committed" if op["committed"] else "not_committed")
        ),
        "execution_count": op["execution_count"],
    }


@app.get("/api/external/mailhog/verify")
def verify_mailhog(message_id: str):
    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:8025/api/v2/messages", timeout=5
        ) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=502, content={"error": str(exc)})

    found = any(
        message_id
        in (item.get("Content", {}).get("Headers", {}).get("Message-ID") or [])
        for item in data.get("items", [])
    )
    if found:
        return {"message_id": message_id, "found": True}
    return JSONResponse(
        status_code=404,
        content={"message_id": message_id, "found": False},
    )
