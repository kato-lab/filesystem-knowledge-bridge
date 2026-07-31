from __future__ import annotations

from contextvars import ContextVar
from dataclasses import asdict, dataclass
from typing import Any, Awaitable, Callable

from kb_common import sanitize_identifier

_CURRENT_HTTP_HEADERS: ContextVar[dict[str, str]] = ContextVar(
    "kb_current_http_headers",
    default={},
)

OPENWEBUI_OWNER_HEADER = "x-openwebui-user-name"


class CaptureHttpHeadersMiddleware:
    """HTTPリクエストヘッダーをTool実行中だけContextVarへ保持するASGI middleware。"""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[..., Awaitable[dict[str, Any]]],
        send: Callable[..., Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        token = _CURRENT_HTTP_HEADERS.set(headers)
        try:
            await self.app(scope, receive, send)
        finally:
            _CURRENT_HTTP_HEADERS.reset(token)


@dataclass(frozen=True)
class OwnerResolution:
    resolved: bool
    method: str
    owner: str | None

    def to_dict(self) -> dict[str, str | bool | None]:
        return asdict(self)


def resolve_owner(explicit_owner: str | None) -> OwnerResolution:
    """明示引数を最優先し、なければ対応クライアントのヘッダーからownerを補完する。"""
    if explicit_owner and explicit_owner.strip():
        return OwnerResolution(
            resolved=True,
            method="explicit",
            owner=sanitize_identifier(explicit_owner),
        )

    forwarded = _CURRENT_HTTP_HEADERS.get().get(OPENWEBUI_OWNER_HEADER, "").strip()
    if forwarded:
        return OwnerResolution(
            resolved=True,
            method="openwebui_header",
            owner=sanitize_identifier(forwarded),
        )

    return OwnerResolution(resolved=False, method="none", owner=None)


def owner_scope_metadata(resolution: OwnerResolution) -> dict[str, Any]:
    searched_personal = resolution.resolved and resolution.owner is not None
    result: dict[str, Any] = {
        "owner_resolution": resolution.to_dict(),
        "searched": {
            "shared": True,
            "personal": searched_personal,
        },
        "hint": None,
    }
    if not searched_personal:
        result["hint"] = (
            "The current user could not be identified, so only shared Knowledge was used. "
            "To include personal Knowledge, specify the owner argument or use a client that "
            "forwards supported user information."
        )
    return result
