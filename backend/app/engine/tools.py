from __future__ import annotations

import asyncio
import email.utils
import json
import re
import smtplib
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
    statement = sql.strip().rstrip(";").strip()
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

    try:
        async with engine.connect() as conn:
            result = await conn.execute(text(statement))
            rows = [_jsonable(dict(row._mapping)) for row in result.fetchall()]
        return {"status": "success", "data": rows, "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "data": None, "error": str(exc)}


def _send_email_sync(to: str, subject: str, body: str) -> dict:
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
        if settings.SMTP_PORT != 465:
            smtp.starttls()
        if settings.SMTP_USERNAME:
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        smtp.send_message(message)
    return {"status": "success", "message_id": message_id}


@tool
async def send_email(to: str, subject: str, body: str) -> dict:
    """Send an email via SMTP. Requires human approval before execution."""
    try:
        result = await asyncio.to_thread(_send_email_sync, to, subject, body)
        return {
            "status": "success",
            "data": {
                "to": to,
                "subject": subject,
                "message_id": result.get("message_id"),
            },
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "data": None, "error": str(exc)}
