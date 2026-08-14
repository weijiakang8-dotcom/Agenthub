from contextlib import asynccontextmanager

import httpx
import redis.asyncio as aioredis
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from sqlalchemy import text

from app.api import api_router
from app.api.websocket import router as websocket_router
from app.api.routes.metrics import router as metrics_router
from app.core.security import decode_token
from app.core.telemetry import setup_telemetry
from app.database import async_session_factory, init_db, master_engine
from app.models import AuditLog
from app.engine.tasks import celery_app  # noqa: F401  # 加载 Celery 配置
from app.config import settings

# 必须在创建 FastAPI 实例前调用，FastAPIInstrumentor 会替换 fastapi.FastAPI 类
setup_telemetry()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 开发环境快速建表；生产环境使用 Alembic。create_all 是幂等操作。
    await init_db()
    yield


app = FastAPI(title="AgentHub API", version="0.1.0", lifespan=lifespan)
FastAPIInstrumentor().instrument_app(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def audit_middleware(request: Request, call_next):
    response = await call_next(request)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        user_id = None
        organization_id = None
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            payload = decode_token(auth.removeprefix("Bearer "))
            if payload and payload.get("sub"):
                try:
                    user_id = uuid.UUID(str(payload["sub"]))
                except (ValueError, TypeError):
                    user_id = None
                org = payload.get("org")
                if org:
                    try:
                        organization_id = uuid.UUID(str(org))
                    except (ValueError, TypeError):
                        organization_id = None

        async with async_session_factory() as session:
            session.add(
                AuditLog(
                    user_id=user_id,
                    organization_id=organization_id,
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    details={},
                )
            )
            await session.commit()

    return response

app.include_router(api_router)
app.include_router(metrics_router)
app.include_router(websocket_router)


@app.get("/")
async def root():
    return {
        "service": "AgentHub API",
        "docs": "/docs",
        "health": "/health",
        "status": "running",
    }


@app.get("/health")
async def health():
    db_ok = redis_ok = llm_ok = False
    try:
        async with master_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        pass

    try:
        client = aioredis.from_url(settings.REDIS_URL)
        await client.ping()
        await client.aclose()
        redis_ok = True
    except Exception:  # noqa: BLE001
        pass

    try:
        async with httpx.AsyncClient(timeout=3) as client:
            await client.get(settings.LLM_BASE_URL)
        llm_ok = True
    except Exception:  # noqa: BLE001
        pass

    healthy = db_ok and redis_ok
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "ok" if healthy else "degraded",
            "database": db_ok,
            "redis": redis_ok,
            "llm": llm_ok,
        },
    )
