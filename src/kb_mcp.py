from __future__ import annotations

import contextlib
import contextvars
import os
import threading
from pathlib import Path
from typing import Any

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from starlette.applications import Starlette
from starlette.routing import Mount

from kb_index import index_directory, sanitize_identifier
from kb_search_core import (
    DEFAULT_SEARCH_LIMIT,
    list_knowledge_projects as list_projects_core,
    read_knowledge_source as read_source_core,
    search_knowledge as search_core,
)

KNOWLEDGE_ROOT = Path(os.environ.get("KNOWLEDGE_ROOT", "/knowledge")).expanduser()
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.environ.get("MCP_PORT", "8000"))

# Initial version intentionally allows only one registration at a time.
_INDEX_LOCK = threading.Lock()
_REQUEST_OWNER: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "knowledge_request_owner", default=None
)


class ForwardedOwnerMiddleware:
    """Capture an owner hint forwarded by Open WebUI or another trusted client.

    This is identification, not authentication. The initial release is intended for
    trusted/internal deployments. A future version can replace this boundary with
    signed headers or authenticated user mapping without changing the tool logic.
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
        forwarded = headers.get("x-knowledge-owner") or headers.get("x-openwebui-user-name")
        token = _REQUEST_OWNER.set(forwarded)
        try:
            await self.app(scope, receive, send)
        finally:
            _REQUEST_OWNER.reset(token)


def resolve_owner(explicit_owner: str | None = None) -> str:
    value = explicit_owner or _REQUEST_OWNER.get()
    if not value:
        raise ToolError(
            "ユーザー名を特定できません。Open WebUIのユーザー情報ヘッダー転送を有効にするか、"
            "エージェント接続でX-Knowledge-Ownerを設定してください。"
        )
    return sanitize_identifier(value)


mcp = FastMCP(
    "filesystem-knowledge-bridge",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
)


@mcp.tool()
def search_knowledge(
    query: str,
    projects: list[str] | None = None,
    limit: int = DEFAULT_SEARCH_LIMIT,
    owner: str | None = None,
) -> list[dict[str, Any]]:
    """Search shared Knowledge and the current user's personal Knowledge.

    Specify projects when the current conversation or agent instruction identifies
    the relevant project. Omit projects only when discovering related projects or
    searching across all accessible Knowledge. The final result count is global,
    not per collection.

    owner is normally inferred from a forwarded request header. The optional owner
    argument exists only as a fallback for trusted clients in the initial version.
    """
    try:
        resolved_owner = resolve_owner(owner)
        return [item.to_dict() for item in search_core(query, resolved_owner, projects, limit)]
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
def list_knowledge_projects(owner: str | None = None) -> list[dict[str, Any]]:
    """List shared projects and the current user's personal projects.

    Use only when the user explicitly asks for a list or a project name cannot be
    determined by normal Knowledge search.
    """
    try:
        return list_projects_core(resolve_owner(owner))
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
def read_knowledge_source(
    source_ref: str,
    start_line: int = 1,
    max_lines: int = 200,
    owner: str | None = None,
) -> dict[str, Any]:
    """Read a limited range from an original text/source file found by search.

    Use this cautiously and only when search chunks do not provide enough context,
    such as when source-code imports, callers, surrounding functions, or complete
    configuration structure must be checked. Pass logical_path from a search result
    as source_ref. Binary documents are intentionally unsupported in the initial version.
    """
    try:
        return read_source_core(source_ref, resolve_owner(owner), start_line, max_lines)
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
def index_personal_knowledge(
    project: str,
    project_id: str | None = None,
    owner: str | None = None,
) -> dict[str, Any]:
    """Index a pre-positioned frozen project as the current user's personal Knowledge.

    The source must already exist at /knowledge/users/<owner>/<project>. This tool
    never creates, overwrites, moves, or deletes original files. If another index
    operation is running, it immediately returns a busy error; retry later.
    """
    owner_id = resolve_owner(owner)
    project_dir_name = project.strip()
    if not project_dir_name or Path(project_dir_name).name != project_dir_name:
        raise ToolError("projectには個人Knowledge領域直下のフォルダ名を指定してください")

    source_root = (KNOWLEDGE_ROOT / "users" / owner_id).resolve()
    source_path = (source_root / project_dir_name).resolve()
    if not source_path.is_relative_to(source_root):
        raise ToolError("個人Knowledge領域外のパスは登録できません")
    if not source_path.is_dir():
        raise ToolError(f"配置済みプロジェクトが見つかりません: {source_path}")

    if not _INDEX_LOCK.acquire(blocking=False):
        raise ToolError("別のナレッジを登録中です。しばらくしてから再度実行してください。")

    try:
        return index_directory(
            source_path,
            shared=False,
            owner=owner_id,
            project_id=project_id or sanitize_identifier(project_dir_name),
        )
    except Exception as exc:
        raise ToolError(
            f"登録に失敗しました。原本は変更されていません。再度登録してください: {exc}"
        ) from exc
    finally:
        _INDEX_LOCK.release()


@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    async with mcp.session_manager.run():
        yield


app = ForwardedOwnerMiddleware(
    Starlette(routes=[Mount("/mcp", app=mcp.streamable_http_app())], lifespan=lifespan)
)


def main() -> None:
    uvicorn.run(app, host=MCP_HOST, port=MCP_PORT)


if __name__ == "__main__":
    main()
