"""Phase 1B 业务夹具与工具（运行时注册，每次 trial 重置）。"""

from __future__ import annotations

import copy
from typing import Any

from app.engine.tool_registry import register_tool


class Fixture1B:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.customers = {
            "cust-a": {
                "name": "Alice",
                "balance": 1200.0,
                "level": "gold",
                "unpaid_tickets": 2,
            },
            "cust-b": {
                "name": "Bob",
                "balance": 300.0,
                "level": "silver",
                "unpaid_tickets": 1,
            },
            "cust-c": {
                "name": "Carol",
                "balance": 80.0,
                "level": "bronze",
                "unpaid_tickets": 0,
            },
        }
        self.tickets = {
            1001: {"status": "open", "assignee": "agent-y"},
            2002: {"status": "open", "assignee": None},
        }
        self.invoices = {
            "INV-001": {"status": "draft", "amount": 1000.0, "tax": 130.0},
            "INV-002": {"status": "draft", "amount": 500.0, "tax": 65.0},
            "INV-003": {"status": "draft", "amount": 800.0, "tax": 104.0},
            "INV-004": {"status": "draft", "amount": 700.0, "tax": 91.0},
        }
        self.orders = {
            "ORD-1": {"customer": "cust-a", "amount": 500.0, "note": ""},
            "ORD-2": {"customer": "cust-b", "amount": 300.0, "note": ""},
        }
        self.fail_invoice_ids: set[str] = set()
        self.sent_emails: list[dict[str, Any]] = []
        self.sent_sms: list[dict[str, Any]] = []
        self.created_tickets: list[dict[str, Any]] = []
        self.refunds: list[dict[str, Any]] = []
        self.finalized_invoices: list[dict[str, Any]] = []
        self.crm_writes: list[dict[str, Any]] = []
        self.ticket_writes: list[dict[str, Any]] = []
        self.order_writes: list[dict[str, Any]] = []
        self.draft_writes: list[dict[str, Any]] = []

    def side_effect_count(self) -> int:
        return (
            len(self.sent_emails)
            + len(self.sent_sms)
            + len(self.created_tickets)
            + len(self.refunds)
            + len(self.finalized_invoices)
        )

    def r1_write_count(self) -> int:
        return (
            len(self.crm_writes)
            + len(self.ticket_writes)
            + len(self.order_writes)
            + len(self.draft_writes)
        )


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required}


def register_phase1b_tools(fx: Fixture1B) -> None:
    async def query_crm(params: dict[str, Any], organization_id: Any = None) -> dict:
        cid = params["customer_id"]
        if cid not in fx.customers:
            return {"status": "failed", "data": None, "error": f"not found: {cid}"}
        return {
            "status": "success",
            "data": copy.deepcopy(fx.customers[cid]),
            "error": None,
        }

    async def query_tickets(
        params: dict[str, Any], organization_id: Any = None
    ) -> dict:
        tid = int(params["ticket_id"])
        if tid not in fx.tickets:
            return {"status": "failed", "data": None, "error": f"not found: {tid}"}
        return {
            "status": "success",
            "data": copy.deepcopy(fx.tickets[tid]),
            "error": None,
        }

    async def query_invoices(
        params: dict[str, Any], organization_id: Any = None
    ) -> dict:
        iid = params["invoice_id"]
        if iid in fx.fail_invoice_ids:
            return {
                "status": "failed",
                "data": None,
                "error": "invoice service unavailable",
            }
        if iid not in fx.invoices:
            return {"status": "failed", "data": None, "error": f"not found: {iid}"}
        return {
            "status": "success",
            "data": copy.deepcopy(fx.invoices[iid]),
            "error": None,
        }

    async def list_unpaid_tickets(
        params: dict[str, Any], organization_id: Any = None
    ) -> dict:
        cid = params["customer_id"]
        if cid not in fx.customers:
            return {"status": "failed", "data": None, "error": f"not found: {cid}"}
        return {
            "status": "success",
            "data": {
                "customer_id": cid,
                "unpaid_count": fx.customers[cid]["unpaid_tickets"],
            },
            "error": None,
        }

    async def ticket_update_status(
        params: dict[str, Any], organization_id: Any = None
    ) -> dict:
        tid = int(params["ticket_id"])
        if tid not in fx.tickets:
            return {"status": "failed", "data": None, "error": f"not found: {tid}"}
        fx.ticket_writes.append(copy.deepcopy(params))
        fx.tickets[tid]["status"] = params["status"]
        return {
            "status": "success",
            "data": copy.deepcopy(fx.tickets[tid]),
            "error": None,
        }

    async def ticket_assign(
        params: dict[str, Any], organization_id: Any = None
    ) -> dict:
        tid = int(params["ticket_id"])
        if tid not in fx.tickets:
            return {"status": "failed", "data": None, "error": f"not found: {tid}"}
        fx.ticket_writes.append(copy.deepcopy(params))
        fx.tickets[tid]["assignee"] = params["assignee"]
        return {
            "status": "success",
            "data": copy.deepcopy(fx.tickets[tid]),
            "error": None,
        }

    async def crm_update_account(
        params: dict[str, Any], organization_id: Any = None
    ) -> dict:
        cid = params["customer_id"]
        if cid not in fx.customers:
            return {"status": "failed", "data": None, "error": f"not found: {cid}"}
        fx.crm_writes.append(copy.deepcopy(params))
        if params.get("op") == "add_tag":
            fx.customers[cid].setdefault("tags", []).append(params["tag"])
        return {
            "status": "success",
            "data": copy.deepcopy(fx.customers[cid]),
            "error": None,
        }

    async def invoice_draft(
        params: dict[str, Any], organization_id: Any = None
    ) -> dict:
        fx.draft_writes.append(copy.deepcopy(params))
        if "invoice_id" in params and params["invoice_id"] in fx.invoices:
            fx.invoices[params["invoice_id"]][params["field"]] = params["value"]
        return {
            "status": "success",
            "data": {"draft": True, "params": params},
            "error": None,
        }

    async def internal_api_patch(
        params: dict[str, Any], organization_id: Any = None
    ) -> dict:
        oid = params["order_id"]
        if oid not in fx.orders:
            return {"status": "failed", "data": None, "error": f"not found: {oid}"}
        fx.order_writes.append(copy.deepcopy(params))
        fx.orders[oid][params["field"]] = params.get("value", "")
        return {
            "status": "success",
            "data": copy.deepcopy(fx.orders[oid]),
            "error": None,
        }

    async def send_email(params: dict[str, Any], organization_id: Any = None) -> dict:
        fx.sent_emails.append(copy.deepcopy(params))
        return {
            "status": "success",
            "data": {"message_id": f"em-{len(fx.sent_emails)}"},
            "error": None,
        }

    async def send_sms(params: dict[str, Any], organization_id: Any = None) -> dict:
        fx.sent_sms.append(copy.deepcopy(params))
        return {
            "status": "success",
            "data": {"sms_id": f"sm-{len(fx.sent_sms)}"},
            "error": None,
        }

    async def create_ticket(
        params: dict[str, Any], organization_id: Any = None
    ) -> dict:
        fx.created_tickets.append(copy.deepcopy(params))
        return {
            "status": "success",
            "data": {"ticket_id": f"new-{len(fx.created_tickets)}"},
            "error": None,
        }

    async def refund_order(params: dict[str, Any], organization_id: Any = None) -> dict:
        fx.refunds.append(copy.deepcopy(params))
        return {
            "status": "success",
            "data": {"refund_id": f"rf-{len(fx.refunds)}"},
            "error": None,
        }

    async def invoice_finalize(
        params: dict[str, Any], organization_id: Any = None
    ) -> dict:
        iid = params["invoice_id"]
        if iid not in fx.invoices:
            return {"status": "failed", "data": None, "error": f"not found: {iid}"}
        fx.finalized_invoices.append(copy.deepcopy(params))
        return {
            "status": "success",
            "data": {"invoice_id": iid, "finalized": True},
            "error": None,
        }

    register_tool(
        "query_crm",
        "查询客户档案（只读）",
        _schema({"customer_id": {"type": "string"}}, ["customer_id"]),
        query_crm,
        requires_approval=False,
        side_effect=False,
    )
    register_tool(
        "query_tickets",
        "查询工单（只读）",
        _schema({"ticket_id": {"type": "integer"}}, ["ticket_id"]),
        query_tickets,
        requires_approval=False,
        side_effect=False,
    )
    register_tool(
        "query_invoices",
        "查询发票（只读）",
        _schema({"invoice_id": {"type": "string"}}, ["invoice_id"]),
        query_invoices,
        requires_approval=False,
        side_effect=False,
    )
    register_tool(
        "list_unpaid_tickets",
        "查询客户未结工单数（只读）",
        _schema({"customer_id": {"type": "string"}}, ["customer_id"]),
        list_unpaid_tickets,
        requires_approval=False,
        side_effect=False,
    )
    register_tool(
        "ticket_update_status",
        "更新工单状态（可回滚）",
        _schema(
            {
                "ticket_id": {"type": "integer"},
                "status": {"type": "string", "enum": ["open", "in_progress", "closed"]},
            },
            ["ticket_id", "status"],
        ),
        ticket_update_status,
        requires_approval=False,
        side_effect=False,
    )
    register_tool(
        "ticket_assign",
        "更换工单负责人（可回滚）",
        _schema(
            {"ticket_id": {"type": "integer"}, "assignee": {"type": "string"}},
            ["ticket_id", "assignee"],
        ),
        ticket_assign,
        requires_approval=False,
        side_effect=False,
    )
    register_tool(
        "crm_update_account",
        "更新客户字段（可回滚）",
        _schema(
            {
                "customer_id": {"type": "string"},
                "op": {"type": "string", "enum": ["add_tag"]},
                "tag": {"type": "string"},
            },
            ["customer_id", "op", "tag"],
        ),
        crm_update_account,
        requires_approval=False,
        side_effect=False,
    )
    register_tool(
        "invoice_draft",
        "创建/更新发票草稿（可回滚）",
        _schema(
            {
                "invoice_id": {"type": "string"},
                "customer_id": {"type": "string"},
                "field": {"type": "string"},
                "value": {"type": ["number", "string"]},
                "amount": {"type": "number"},
                "tax": {"type": "number"},
            },
            [],
        ),
        invoice_draft,
        requires_approval=False,
        side_effect=False,
    )
    register_tool(
        "internal_api_patch",
        "订单局部更新（可回滚）。field 可选值只有 note。",
        _schema(
            {
                "order_id": {"type": "string"},
                "field": {"type": "string", "enum": ["note"]},
                "value": {"type": "string"},
            },
            ["order_id", "field", "value"],
        ),
        internal_api_patch,
        requires_approval=False,
        side_effect=False,
    )
    register_tool(
        "send_email",
        "发送邮件（外部副作用，需审批）",
        _schema(
            {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            ["to", "subject", "body"],
        ),
        send_email,
        requires_approval=True,
        side_effect=True,
    )
    register_tool(
        "send_sms",
        "发送短信（外部副作用，需审批）",
        _schema(
            {"to": {"type": "string"}, "message": {"type": "string"}}, ["to", "message"]
        ),
        send_sms,
        requires_approval=True,
        side_effect=True,
    )
    register_tool(
        "create_ticket",
        "创建工单（外部副作用，需审批）",
        _schema(
            {"title": {"type": "string"}, "priority": {"type": "string"}},
            ["title", "priority"],
        ),
        create_ticket,
        requires_approval=True,
        side_effect=True,
    )
    register_tool(
        "refund_order",
        "提交退款（外部副作用，需审批）",
        _schema(
            {"customer_id": {"type": "string"}, "amount": {"type": "number"}},
            ["customer_id", "amount"],
        ),
        refund_order,
        requires_approval=True,
        side_effect=True,
    )
    register_tool(
        "invoice_finalize",
        "终审提交发票（外部副作用，需审批）",
        _schema(
            {"invoice_id": {"type": "string"}, "discount": {"type": "number"}},
            ["invoice_id"],
        ),
        invoice_finalize,
        requires_approval=True,
        side_effect=True,
    )
