from __future__ import annotations

from fastmcp import FastMCP

from .config import load_config
from .rag_core import get_index

mcp = FastMCP("Filesystem Knowledge Bridge")


@mcp.tool()
def search_knowledge(query: str, top_k: int | None = None) -> str:
    """Search indexed filesystem knowledge.

    Use this when you need information from laboratory/project files.
    The response includes an answer and source file paths.
    """
    cfg = load_config()
    index = get_index(cfg)
    k = top_k or cfg.search.similarity_top_k
    query_engine = index.as_query_engine(similarity_top_k=k)
    response = query_engine.query(query)

    lines = ["# Answer", str(response), "", "# Sources"]
    for source in response.source_nodes:
        meta = source.node.metadata
        lines.append(f"- {meta.get('source_path', '(unknown)')} score={source.score}")
    return "
".join(lines)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
