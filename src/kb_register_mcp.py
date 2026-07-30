from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from kb_common import create_transport_security

mcp = FastMCP(
    "filesystem-knowledge-bridge register",
    json_response=True,
    transport_security=create_transport_security(8001),
)


@mcp.tool()
def list_incoming(owner: str):
    """incoming/users/<owner> に配置済みの登録候補projectを一覧表示します。"""
    from kb_register_core import list_incoming as list_projects

    return list_projects(owner)


@mcp.tool()
def register_incoming_project(owner: str, project: str, project_id: str | None = None):
    """incomingに配置済みのprojectを原本領域へコピーし、個人Knowledgeとして登録します。

    projectはユーザー向けの名前です。project_idは内部UUIDで、通常は省略してください。
    省略時はRegister側でUUIDv4を生成します。incoming原本は削除しません。
    """
    from kb_register_core import register_incoming_project as register

    return register(owner, project, project_id)


@mcp.tool()
def reindex_stored_project(owner: str, project: str, project_id: str | None = None):
    """保存済み原本からQdrant Collectionを削除・再構築します。

    保存済みの.kb_project.jsonから同じproject_idを再利用します。
    通常はproject_idを省略してください。原本は変更しません。
    """
    from kb_register_core import reindex_stored_project as reindex

    return reindex(owner, project, project_id)


def main() -> None:
    mcp.settings.host = os.environ.get("MCP_HOST", "0.0.0.0")
    mcp.settings.port = int(os.environ.get("MCP_PORT", "8001"))
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
