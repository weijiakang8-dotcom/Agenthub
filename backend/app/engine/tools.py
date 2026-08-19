from __future__ import annotations

import asyncio
import email.utils
import hashlib
import json
import re
import smtplib
import threading
import uuid
from email.message import EmailMessage
from typing import Any

import httpx
from langchain_core.tools import tool
from sqlalchemy import text

from app.config import settings
from app.database import engine

_SELECT_RE = re.compile(r"^\s*SELECT\b", re.IGNORECASE)
_DANGEROUS_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|COPY|GRANT|REVOKE|CALL|DO|VACUUM|REINDEX)\b",
    re.IGNORECASE,
)
_FORBIDDEN_SQL_RE = re.compile(
    r"[();]|--|/\*|\bJOIN\b|\bUNION\b|\bINTO\b|\bGROUP\s+BY\b|\bORDER\s+BY\b|\bHAVING\b",
    re.IGNORECASE,
)

# query_db 只允许访问这些带 organization_id 的业务表。
# 敏感表（users / organizations / model_configs / api_keys / audit_logs 等）被自动拒绝。
_QUERY_DB_ALLOWED_TABLES = frozenset(
    {"agents", "workflows", "executions", "documents", "tool_calls"}
)
_QUERY_DB_MAX_ROWS = 100

_SENT_EMAIL_HASHES: set[str] = set()
_EMAIL_HASH_LOCK = threading.Lock()


def _coerce_org_id(organization_id: Any) -> uuid.UUID | None:
    if organization_id is None:
        return None
    if isinstance(organization_id, uuid.UUID):
        return organization_id
    try:
        return uuid.UUID(str(organization_id))
    except (ValueError, TypeError):
        return None


def _parse_scoped_select(sql: str) -> tuple[str, str, str | None, int | None] | None:
    """只接受：SELECT <cols> FROM <table> [WHERE <cond>] [LIMIT <n>] 单表结构。"""
    match = re.match(
        r"^\s*SELECT\s+(?P<select>.+?)\s+FROM\s+"
        r"(?P<table>[A-Za-z_][A-Za-z0-9_]*)\s*(?P<rest>.*)$",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None

    select_list = match.group("select").strip()
    table = match.group("table").lower()
    rest = match.group("rest").strip()
    where_condition: str | None = None
    limit_value: int | None = None

    if rest:
        where_match = re.match(
            r"^WHERE\s+(?P<where>.+)$", rest, re.IGNORECASE | re.DOTALL
        )
        if where_match:
            where_part = where_match.group("where").strip()
            limit_match = re.search(
                r"\s+LIMIT\s+(?P<limit>\d+)\s*$", where_part, re.IGNORECASE
            )
            if limit_match:
                limit_value = int(limit_match.group("limit"))
                where_part = where_part[: limit_match.start()].strip()
            where_condition = where_part
        else:
            limit_match = re.match(r"^LIMIT\s+(?P<limit>\d+)\s*$", rest, re.IGNORECASE)
            if limit_match:
                limit_value = int(limit_match.group("limit"))
            else:
                return None

    return select_list, table, where_condition, limit_value


def _build_scoped_sql(
    select_list: str,
    table: str,
    where_condition: str | None,
    limit_value: int | None,
) -> str:
    statement = f"SELECT {select_list} FROM {table}"
    if where_condition:
        statement += f" WHERE ({where_condition}) AND organization_id = :org"
    else:
        statement += " WHERE organization_id = :org"
    if limit_value is not None:
        statement += f" LIMIT {limit_value}"
    return statement


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


@tool
async def search_web(query: str) -> dict:
    """Search the web for the given query, preferring Tavily then DuckDuckGo."""
    if settings.TAVILY_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": settings.TAVILY_API_KEY,
                        "query": query,
                        "max_results": 5,
                    },
                )
                response.raise_for_status()
                data = response.json()
            return {"status": "success", "data": data.get("results", []), "error": None}
        except Exception as exc:  # noqa: BLE001
            return {"status": "failed", "data": None, "error": str(exc)}

    try:
        from duckduckgo_search import DDGS

        def _ddg() -> list[dict]:
            with DDGS() as ddg:
                return list(ddg.text(query, max_results=5))

        results = await asyncio.to_thread(_ddg)
        summaries = [
            {
                "title": item.get("title", ""),
                "url": item.get("href", ""),
                "snippet": item.get("body", ""),
            }
            for item in results[:5]
        ]
        return {"status": "success", "data": summaries, "error": None}
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "failed",
            "data": None,
            "error": f"TAVILY_API_KEY not configured and DuckDuckGo fallback failed: {exc}",
        }


@tool
async def query_db(sql: str) -> dict:
    """Run a single read-only SELECT query against the AgentHub database."""
    # 实际执行统一走 run_query_db，租户由执行引擎服务端注入，不允许 Agent 自行决定。
    return await run_query_db(sql, None)


async def run_query_db(sql: str, organization_id: Any) -> dict:
    """以强制租户边界执行 query_db：只读、单表、白名单、自动注入 org 谓词。"""
    org_id = _coerce_org_id(organization_id)
    if org_id is None:
        return {
            "status": "failed",
            "data": None,
            "error": "tenant context required",
        }

    statement = (sql or "").strip().rstrip(";").strip()
    if (
        not _SELECT_RE.match(statement)
        or _DANGEROUS_RE.search(statement)
        or ";" in statement
    ):
        return {
            "status": "failed",
            "data": None,
            "error": "Only a single read-only SELECT is allowed",
        }
    if _FORBIDDEN_SQL_RE.search(statement):
        return {
            "status": "failed",
            "data": None,
            "error": "Unsupported SQL construct",
        }

    parsed = _parse_scoped_select(statement)
    if parsed is None:
        return {
            "status": "failed",
            "data": None,
            "error": "Only single-table SELECT ... FROM <table> [WHERE ...] [LIMIT n] is allowed",
        }

    select_list, table, where_condition, limit_value = parsed
    if table not in _QUERY_DB_ALLOWED_TABLES:
        return {
            "status": "failed",
            "data": None,
            "error": f"Table '{table}' is not accessible",
        }

    if limit_value is None:
        limit_value = _QUERY_DB_MAX_ROWS
    limit_value = min(limit_value, _QUERY_DB_MAX_ROWS)

    scoped = _build_scoped_sql(select_list, table, where_condition, limit_value)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text(scoped), {"org": str(org_id)})
            rows = [_jsonable(dict(row._mapping)) for row in result.fetchall()]
        return {"status": "success", "data": rows, "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "data": None, "error": str(exc)}


def _send_email_sync(to: str, subject: str, body: str) -> dict:
    content_hash = hashlib.sha256(f"{to}\0{subject}\0{body}".encode()).hexdigest()
    with _EMAIL_HASH_LOCK:
        if content_hash in _SENT_EMAIL_HASHES:
            return {"status": "duplicate", "message_id": None}

    message = EmailMessage()
    message["From"] = settings.SMTP_FROM
    message["To"] = to
    message["Subject"] = subject
    message_id = email.utils.make_msgid(domain="agenthub.local")
    message["Message-ID"] = message_id
    message.set_content(body)

    if settings.SMTP_PORT == 465:
        smtp_cls = smtplib.SMTP_SSL
    else:
        smtp_cls = smtplib.SMTP

    with smtp_cls(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as smtp:
        if settings.SMTP_PORT != 465 and settings.SMTP_USERNAME:
            smtp.starttls()
        if settings.SMTP_USERNAME:
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        smtp.send_message(message)
    with _EMAIL_HASH_LOCK:
        _SENT_EMAIL_HASHES.add(content_hash)
    return {"status": "success", "message_id": message_id}


@tool
async def send_email(to: str, subject: str, body: str) -> dict:
    """Send an email via the configured provider (SMTP preferred, Resend fallback).

    Requires human approval before execution. 复用系统已有的邮件 Provider 配置，
    不引入新邮件架构。
    """
    try:
        if settings.SMTP_HOST:
            result = await asyncio.to_thread(_send_email_sync, to, subject, body)
        else:
            from app.core.email import send_email as _send_via_email_service

            result = await _send_via_email_service(to, subject, body)
        if result.get("status") == "duplicate":
            return {
                "status": "duplicate",
                "data": {"to": to, "subject": subject},
                "error": None,
            }
        if result.get("ok") is False:
            return {
                "status": "failed",
                "data": None,
                "error": str(result.get("error")),
            }
        message_id = result.get("message_id") or (result.get("data") or {}).get("id")
        return {
            "status": "success",
            "data": {
                "to": to,
                "subject": subject,
                "message_id": message_id,
            },
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "data": None, "error": str(exc)}
