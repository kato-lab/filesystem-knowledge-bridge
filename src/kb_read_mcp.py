from __future__ import annotations

import contextlib
import os
from typing import Any

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from starlette.applications import Starlette
from starlette.routing import Mount

from kb_mcp_common import ForwardedOwnerMiddleware, resolve_owner
from kb_search_core import (
    DEFAULT_SEARCH_LIMIT,
    list_knowledge_projects as list_projects_core,
    read_knowledge_source as read_source_core,
    search_knowledge as search_core,
)

HOST = os.environ.get("KB_READ_MCP_HOST", "0.0.0.0")
PORT = int(os.environ.get("KB_READ_MCP_PORT", "8000"))

mcp = FastMCP(
    "filesystem-knowledge-read",
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

    Specify projects when known. Omit projects only for cross-project discovery.
    The returned limit is global across all searched collections.
    """
    try:
        return [item.to_dict() for item in search_core(query, resolve_owner(owner), projects, limit)]
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
def list_knowledge_projects(owner: str | None = None) -> list[dict[str, Any]]:
    """List shared projects and the current user's personal projects."""
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
    """Read a limited range of a text/source original referenced by search.

    Use only when search chunks are insufficient. Binary documents are not read.
    """
    try:
        return read_source_core(source_ref, resolve_owner(owner), start_line, max_lines)
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(str(exc)) from exc


@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    async with mcp.session_manager.run():
        yield


app = ForwardedOwnerMiddleware(
    Starlette(routes=[Mount("/mcp", app=mcp.streamable_http_app())], lifespan=lifespan)
)


def main() -> None:
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
