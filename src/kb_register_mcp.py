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
from kb_register_core import import_incoming_project, index_stored_project, list_incoming_projects

HOST = os.environ.get("KB_REGISTER_MCP_HOST", "0.0.0.0")
PORT = int(os.environ.get("KB_REGISTER_MCP_PORT", "8001"))

mcp = FastMCP(
    "filesystem-knowledge-register",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
)


@mcp.tool()
def list_incoming(owner: str | None = None) -> list[str]:
    """List project directories waiting under /incoming/users/<owner>."""
    try:
        return list_incoming_projects(resolve_owner(owner))
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
def register_incoming_project(
    project: str,
    project_id: str | None = None,
    owner: str | None = None,
) -> dict[str, Any]:
    """Copy a pre-positioned incoming project into protected storage and index it.

    The incoming directory is preserved. Existing stored originals are never
    overwritten or deleted. Concurrent registration is rejected immediately.
    """
    try:
        return import_incoming_project(resolve_owner(owner), project, project_id)
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
def reindex_stored_project(
    project: str,
    project_id: str | None = None,
    owner: str | None = None,
) -> dict[str, Any]:
    """Rebuild Qdrant from an already stored original without changing files."""
    try:
        return index_stored_project(resolve_owner(owner), project, project_id)
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
