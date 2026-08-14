from fastapi import APIRouter

from app.api.routes import (
    agents,
    alert_rules,
    alerts,
    audit_logs,
    auth,
    conversations,
    eval as eval_routes,
    executions,
    models,
    notifications,
    tasks,
    tool_calls,
    usage,
    workflow_templates,
    workflows,
)


api_router = APIRouter(prefix="/api")
api_router.include_router(agents.router)
api_router.include_router(workflows.router)
api_router.include_router(executions.router)
api_router.include_router(tool_calls.router)
api_router.include_router(alerts.router)
api_router.include_router(alert_rules.router)
api_router.include_router(audit_logs.router)
api_router.include_router(auth.router)
api_router.include_router(conversations.router)
api_router.include_router(eval_routes.router)
api_router.include_router(models.router)
api_router.include_router(notifications.router)
api_router.include_router(usage.router)
api_router.include_router(tasks.router)
api_router.include_router(workflow_templates.router)


__all__ = ["api_router"]
