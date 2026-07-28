from __future__ import annotations

import contextvars

from mcp.server.fastmcp.exceptions import ToolError

from kb_common import sanitize_identifier

_REQUEST_OWNER: contextvars.ContextVar[str | None] = contextvars.ContextVar("knowledge_owner", default=None)


class ForwardedOwnerMiddleware:
    """Read a trusted owner hint from an HTTP header.

    This is user identification only, not a complete authentication mechanism.
    Keep the service on a trusted network until proper authentication is added.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = {
            key.decode("latin-1").lower(): value.decode("utf-8", errors="replace")
            for key, value in scope.get("headers", [])
        }
        token = _REQUEST_OWNER.set(headers.get("x-knowledge-owner") or headers.get("x-openwebui-user-name"))
        try:
            await self.app(scope, receive, send)
        finally:
            _REQUEST_OWNER.reset(token)


def resolve_owner(explicit_owner: str | None = None) -> str:
    value = explicit_owner or _REQUEST_OWNER.get()
    if not value:
        raise ToolError("ユーザー名を特定できません。X-Knowledge-Ownerヘッダーを設定してください。")
    return sanitize_identifier(value)
