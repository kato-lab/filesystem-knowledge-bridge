from __future__ import annotations

import argparse

from .config import load_config
from .rag_core import get_index


def search_text(query: str, owner: str | None = None, top_k: int | None = None) -> str:
    cfg = load_config()
    index = get_index(cfg)
    query_engine = index.as_query_engine(similarity_top_k=top_k or cfg.search.similarity_top_k)
    response = query_engine.query(query)
    lines = ["# Answer", "", str(response), "", "# Sources"]
    for source in response.source_nodes:
        meta = source.node.metadata
        if owner and meta.get("owner") not in (owner, cfg.knowledge.shared_owner):
            continue
        lines.append(f"- owner={meta.get('owner')} path={meta.get('source_path')} score={source.score}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="+")
    parser.add_argument("--owner", default=None)
    parser.add_argument("--top-k", type=int, default=None)
    args = parser.parse_args()
    print(search_text(" ".join(args.query), owner=args.owner, top_k=args.top_k))


if __name__ == "__main__":
    main()
