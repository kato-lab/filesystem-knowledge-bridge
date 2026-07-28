from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("filesystem-knowledge-bridge read", json_response=True)


@mcp.tool()
def search_knowledge(query: str, owner: str | None = None, projects: list[str] | None = None, limit: int = 5):
    """共有Knowledgeと、owner指定時は本人の個人Knowledgeを検索します。projectsを省略すると横断検索します。"""
    from kb_search_core import search_knowledge as search

    return search(query, owner=owner, projects=projects, limit=limit)


@mcp.tool()
def list_knowledge_projects(owner: str | None = None):
    """参照可能な共有projectと、owner指定時は本人の個人projectを一覧表示します。"""
    from kb_search_core import list_knowledge_projects as list_projects

    return list_projects(owner=owner)


@mcp.tool()
def read_knowledge_source(
    scope: str,
    project: str,
    relative_path: str,
    owner: str | None = None,
    start_line: int = 1,
    max_lines: int = 200,
):
    """検索チャンクだけでは前後関係が不足する場合に限り、テキスト形式の原本を範囲指定で参照します。"""
    from kb_search_core import read_knowledge_source as read_source

    return read_source(
        scope=scope,
        owner=owner,
        project=project,
        relative_path=relative_path,
        start_line=start_line,
        max_lines=max_lines,
    )


def main() -> None:
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8000"))
    mcp.run(transport="streamable-http", host=host, port=port)


if __name__ == "__main__":
    main()
