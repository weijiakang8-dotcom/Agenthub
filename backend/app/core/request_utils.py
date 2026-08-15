from __future__ import annotations

from fastapi import Request


def get_client_ip(request: Request) -> str:
    """从代理请求头解析真实客户端 IP，兼容 Nginx / Ingress。"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()

    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    return request.client.host if request.client else "unknown"
