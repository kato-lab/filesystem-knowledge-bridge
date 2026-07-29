#!/usr/bin/env python3
"""filesystem-knowledge-bridge MCP smoke/integration test client.

The project MCP dependency is used directly. Node.js and MCP Inspector are not
required.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
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


async def with_session(
    url: str,
    callback: Callable[[ClientSession], Awaitable[Any]],
) -> Any:
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


# Utility --------------------------------------------------------------------
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


# Read MCP -------------------------------------------------------------------
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


async def command_read(args: argparse.Namespace) -> None:
    arguments: dict[str, Any] = {
        "scope": args.scope,
        "project": args.project,
        "relative_path": args.path,
        "owner": args.owner,
        "start_line": args.start_line,
        "max_lines": args.max_lines,
    }
    result = await call_tool(args.read_url, "read_knowledge_source", arguments)
    if result_is_error(result):
        raise RuntimeError("原本参照がエラーになりました")


# Register MCP ---------------------------------------------------------------
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
        raise RuntimeError("登録に失敗しました")

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="filesystem-knowledge-bridge MCPテストクライアント",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""コマンド分類:
  Utility      inspect
  Read MCP     projects, search, read
  Register MCP incoming, register, reindex
""",
    )
    parser.add_argument("--read-url", default=DEFAULT_READ_URL)
    parser.add_argument("--register-url", default=DEFAULT_REGISTER_URL)

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Utility
    subparsers.add_parser("inspect", help="[Utility] 両MCPのTool一覧を確認")

    # Read MCP
    projects = subparsers.add_parser("projects", help="[Read] 参照可能projectを一覧表示")
    projects.add_argument("--owner")

    search = subparsers.add_parser("search", help="[Read] Knowledgeを検索")
    search.add_argument("query")
    search.add_argument("--owner")
    search.add_argument("--project", action="append")
    search.add_argument("--limit", type=int, default=5)

    read = subparsers.add_parser("read", help="[Read] テキスト原本を範囲指定で参照")
    read.add_argument("--scope", choices=("shared", "personal"), required=True)
    read.add_argument("--owner")
    read.add_argument("--project", required=True)
    read.add_argument("--path", required=True, help="project内の相対パス")
    read.add_argument("--start-line", type=int, default=1)
    read.add_argument("--max-lines", type=int, default=200)

    # Register MCP
    incoming = subparsers.add_parser("incoming", help="[Register] incoming候補を一覧表示")
    incoming.add_argument("--owner", required=True)

    register = subparsers.add_parser("register", help="[Register] incoming projectを登録")
    register.add_argument("--owner", required=True)
    register.add_argument("--project", required=True)
    register.add_argument("--project-id")
    register.add_argument(
        "--check-duplicate",
        action="store_true",
        help="直後に同じ登録を再実行し、拒否されることを確認",
    )

    reindex = subparsers.add_parser(
        "reindex", help="[Register] 保存済み原本からCollectionを再構築"
    )
    reindex.add_argument("--owner", required=True)
    reindex.add_argument("--project", required=True)
    reindex.add_argument("--project-id")

    return parser


async def async_main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    commands = {
        "inspect": command_inspect,
        "projects": command_projects,
        "search": command_search,
        "read": command_read,
        "incoming": command_incoming,
        "register": command_register,
        "reindex": command_reindex,
    }
    await commands[args.command](args)


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("中断しました", file=sys.stderr)
        raise SystemExit(130)
    except BaseExceptionGroup as exc:
        import traceback

        traceback.print_exception(exc)
        raise SystemExit(1)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
