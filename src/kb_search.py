from __future__ import annotations

import argparse
import json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Qdrant Knowledge検索ツール")
    parser.add_argument("query", help="検索文")
    parser.add_argument("--owner", help="共有Knowledgeに加えて検索する個人owner")
    parser.add_argument("--project", dest="projects", action="append", help="検索対象project。複数指定可")
    parser.add_argument("--limit", type=int, default=5, help="最終検索結果数（最大10）")
    parser.add_argument("--json", action="store_true", help="JSONで出力")
    parser.add_argument("--full-text", action="store_true", help="本文を省略せず表示")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    from kb_search_core import search_knowledge

    results = search_knowledge(args.query, owner=args.owner, projects=args.projects, limit=args.limit)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    for index, result in enumerate(results, start=1):
        text = result["text"] or ""
        if not args.full_text and len(text) > 500:
            text = text[:500] + "..."
        print(f"[{index}] score={result['score']:.4f} {result['collection']}")
        print(f"    {result.get('relative_path') or '-'}#chunk-{result.get('chunk_index')}")
        print(f"    {text}\n")


if __name__ == "__main__":
    main()
