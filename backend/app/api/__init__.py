from fastapi import APIRouter

from app.api.routes import agents, executions, tool_calls, workflows


api_router = APIRouter(prefix="/api")
api_router.include_router(agents.router)
api_router.include_router(workflows.router)
api_router.include_router(executions.router)
api_router.include_router(tool_calls.router)


__all__ = ["api_router"]
