from __future__ import annotations

import sys

from .config import load_config
from .rag_core import get_index


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m fkb.search 'your query'")
        raise SystemExit(1)

    query = " ".join(sys.argv[1:])
    cfg = load_config()
    index = get_index(cfg)
    query_engine = index.as_query_engine(similarity_top_k=cfg.search.similarity_top_k)
    response = query_engine.query(query)

    print("
# Answer
")
    print(str(response))
    print("
# Sources
")
    for source in response.source_nodes:
        meta = source.node.metadata
        print(f"- {meta.get('source_path', '(unknown)')} score={source.score}")


if __name__ == "__main__":
    main()
