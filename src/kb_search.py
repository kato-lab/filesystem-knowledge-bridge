from __future__ import annotations

import argparse
import getpass
import json
import sys

from kb_index import sanitize_identifier
from kb_search_core import DEFAULT_SEARCH_LIMIT, search_knowledge


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Qdrant Knowledge検索ツール")
    parser.add_argument("query", help="検索文")
    parser.add_argument("--owner", help="参照する個人Knowledgeのowner。省略時はOSユーザ")
    parser.add_argument("--project", action="append", dest="projects", help="検索対象project。複数指定可")
    parser.add_argument("--limit", type=int, default=DEFAULT_SEARCH_LIMIT, help="最終的に返す検索結果数")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")
    parser.add_argument("--full-text", action="store_true", help="チャンク本文を省略せず表示")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    owner = sanitize_identifier(args.owner or getpass.getuser() or "unknown")
    try:
        results = search_knowledge(args.query, owner, args.projects, args.limit)
    except Exception as exc:
        print(f"❌ 検索失敗: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.json:
        print(json.dumps([result.to_dict() for result in results], ensure_ascii=False, indent=2))
        return

    if not results:
        print("該当するKnowledgeは見つかりませんでした")
        return

    for number, result in enumerate(results, start=1):
        text = result.text if args.full_text else result.text.replace("\n", " ")[:500]
        print(f"[{number}] score={result.score:.4f} {result.scope}:{result.project_id}")
        print(f"    {result.relative_path}#chunk-{result.chunk_index}")
        print(f"    {text}")
        print()


if __name__ == "__main__":
    main()
