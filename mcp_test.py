#!/usr/bin/env python3
"""filesystem-knowledge-bridge MCP smoke/integration test client.

Uses the MCP Python SDK already declared by the project. No Node.js or npx is
required.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


DEFAULT_READ_URL = "http://localhost:8000/mcp"
DEFAULT_REGISTER_URL = "http://localhost:8001/mcp"


def to_jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    return value


def print_result(title: str, value: Any) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(to_jsonable(value), ensure_ascii=False, indent=2))


async def with_session(url: str, callback):
    async with streamable_http_client(url) as streams:
        read_stream, write_stream = streams[0], streams[1]
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            return await callback(session)


async def list_tools(url: str) -> list[str]:
    async def run(session: ClientSession) -> list[str]:
        response = await session.list_tools()
        print_result(f"Tools: {url}", response)
        return [tool.name for tool in response.tools]

    return await with_session(url, run)


async def call_tool(url: str, name: str, arguments: dict[str, Any]) -> Any:
    async def run(session: ClientSession) -> Any:
        result = await session.call_tool(name, arguments=arguments)
        print_result(f"{name} {arguments}", result)
        return result

    return await with_session(url, run)


def result_is_error(result: Any) -> bool:
    return bool(getattr(result, "isError", False) or getattr(result, "is_error", False))


async def command_inspect(args: argparse.Namespace) -> None:
    read_tools = await list_tools(args.read_url)
    register_tools = await list_tools(args.register_url)

    expected_read = {
        "search_knowledge",
        "list_knowledge_projects",
        "read_knowledge_source",
    }
    expected_register = {
        "list_incoming",
        "register_incoming_project",
        "reindex_stored_project",
    }

    missing_read = expected_read - set(read_tools)
    missing_register = expected_register - set(register_tools)
    if missing_read or missing_register:
        raise RuntimeError(
            f"Tool不足: read={sorted(missing_read)}, "
            f"register={sorted(missing_register)}"
        )

    print("\nMCP Tool一覧: OK")


async def command_incoming(args: argparse.Namespace) -> None:
    await call_tool(
        args.register_url,
        "list_incoming",
        {"owner": args.owner},
    )


async def command_register(args: argparse.Namespace) -> None:
    await call_tool(
        args.register_url,
        "list_incoming",
        {"owner": args.owner},
    )
    result = await call_tool(
        args.register_url,
        "register_incoming_project",
        {
            "owner": args.owner,
            "project": args.project,
            "project_id": args.project_id,
        },
    )
    if result_is_error(result):
        raise RuntimeError("最初の登録がエラーになりました")

    if args.check_duplicate:
        duplicate = await call_tool(
            args.register_url,
            "register_incoming_project",
            {
                "owner": args.owner,
                "project": args.project,
                "project_id": args.project_id,
            },
        )
        if not result_is_error(duplicate):
            raise RuntimeError("同名原本の再登録が拒否されませんでした")
        print("\n同名原本の再登録拒否: OK")


async def command_reindex(args: argparse.Namespace) -> None:
    result = await call_tool(
        args.register_url,
        "reindex_stored_project",
        {
            "owner": args.owner,
            "project": args.project,
            "project_id": args.project_id,
        },
    )
    if result_is_error(result):
        raise RuntimeError("保存済み原本からの再登録がエラーになりました")


async def command_projects(args: argparse.Namespace) -> None:
    await call_tool(
        args.read_url,
        "list_knowledge_projects",
        {"owner": args.owner},
    )


async def command_search(args: argparse.Namespace) -> None:
    arguments: dict[str, Any] = {
        "query": args.query,
        "owner": args.owner,
        "limit": args.limit,
    }
    if args.project:
        arguments["projects"] = args.project
    await call_tool(args.read_url, "search_knowledge", arguments)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="filesystem-knowledge-bridge MCPテストクライアント"
    )
    parser.add_argument("--read-url", default=DEFAULT_READ_URL)
    parser.add_argument("--register-url", default=DEFAULT_REGISTER_URL)

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("inspect", help="両MCPのTool一覧を確認")

    incoming = subparsers.add_parser("incoming", help="incoming候補を一覧表示")
    incoming.add_argument("--owner", required=True)

    register = subparsers.add_parser("register", help="incoming projectを登録")
    register.add_argument("--owner", required=True)
    register.add_argument("--project", required=True)
    register.add_argument("--project-id")
    register.add_argument(
        "--check-duplicate",
        action="store_true",
        help="直後に同じ登録を再実行し、拒否されることを確認",
    )

    reindex = subparsers.add_parser(
        "reindex", help="保存済み原本からCollectionを再構築"
    )
    reindex.add_argument("--owner", required=True)
    reindex.add_argument("--project", required=True)
    reindex.add_argument("--project-id")

    projects = subparsers.add_parser("projects", help="参照可能projectを一覧表示")
    projects.add_argument("--owner")

    search = subparsers.add_parser("search", help="Knowledgeを検索")
    search.add_argument("query")
    search.add_argument("--owner")
    search.add_argument("--project", action="append")
    search.add_argument("--limit", type=int, default=5)

    return parser


async def async_main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    commands = {
        "inspect": command_inspect,
        "incoming": command_incoming,
        "register": command_register,
        "reindex": command_reindex,
        "projects": command_projects,
        "search": command_search,
    }
    await commands[args.command](args)


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("中断しました", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
