from __future__ import annotations

import argparse
import getpass
import json
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="登録済みKnowledge検索ツール")
    parser.add_argument("query", help="検索文")
    parser.add_argument("--owner", help="個人Knowledgeのowner。省略時はOSユーザ")
    parser.add_argument("--project", dest="projects", action="append", help="検索対象project。複数指定可")
    parser.add_argument("--limit", type=int, default=5, help="全Collectionを統合した最終件数")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")
    parser.add_argument("--full-text", action="store_true", help="本文を省略せず表示")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    from kb_common import sanitize_identifier
    from kb_search_core import search_knowledge

    owner = sanitize_identifier(args.owner or getpass.getuser() or "unknown")
    try:
        results = search_knowledge(args.query, owner, args.projects, args.limit)
    except Exception as exc:
        print(f"❌ {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.json:
        print(json.dumps([item.to_dict() for item in results], ensure_ascii=False, indent=2))
        return

    for index, item in enumerate(results, start=1):
        text = item.text if args.full_text else item.text.replace("\n", " ")[:500]
        print(f"[{index}] score={item.score:.4f} {item.collection}")
        print(f"    {item.relative_path}#chunk-{item.chunk_index}")
        print(f"    {text}\n")


if __name__ == "__main__":
    main()
