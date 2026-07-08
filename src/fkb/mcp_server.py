from __future__ import annotations

from fastmcp import FastMCP

from .search import search_text

mcp = FastMCP("Filesystem Knowledge Bridge")


@mcp.tool()
def search_knowledge(query: str, owner: str | None = None, top_k: int | None = None) -> str:
    """Search indexed filesystem knowledge.

    owner can be used to restrict displayed sources to a specific user and shared knowledge.
    """
    return search_text(query, owner=owner, top_k=top_k)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
