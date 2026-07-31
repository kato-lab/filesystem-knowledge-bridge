from __future__ import annotations

import os
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from kb_client_context import CaptureHttpHeadersMiddleware, owner_scope_metadata, resolve_owner
from kb_common import create_transport_security

mcp = FastMCP(
    "filesystem-knowledge-bridge read",
    json_response=True,
    transport_security=create_transport_security(8000),
)


@mcp.tool(
    description=(
        "登録済みのプロジェクトKnowledgeを意味検索します。ownerを明示すると共有Knowledgeと"
        "そのownerの個人Knowledgeを検索します。ownerを省略した場合、対応クライアントから"
        "利用者情報が転送されていれば現在の利用者をownerとして自動補完し、補完できなければ"
        "共有Knowledgeだけを検索します。対象プロジェクトが既知ならprojectsを指定して局所検索し、"
        "未知ならprojectsを省略して候補を探してください。検索結果のチャンクだけでは前後関係が"
        "不足する場合に限り、結果に含まれるproject_nameとrelative_pathを使って"
        "read_knowledge_sourceを呼び出してください。"
    )
)
def search_knowledge(
    query: Annotated[
        str,
        Field(
            description=(
                "意味検索する質問または検索語。利用者の目的が伝わる具体的な自然言語を指定する。"
                "空文字は指定しない。"
            ),
            min_length=1,
        ),
    ],
    owner: Annotated[
        str | None,
        Field(
            description=(
                "対象とする個人Knowledgeのownerアカウント名。別ownerを明示する場合に指定する。"
                "省略時は、対応クライアントから転送された現在の利用者情報で自動補完する。"
                "補完できない場合は共有Knowledgeだけを検索し、その事実を結果のhintとフラグで返す。"
            )
        ),
    ] = None,
    projects: Annotated[
        list[str] | None,
        Field(
            description=(
                "検索対象を限定するproject_nameまたはproject_idの一覧。現在扱っているプロジェクトが"
                "分かっている場合は指定する。プロジェクトを探す段階や横断検索では省略する。"
                "表記はlist_knowledge_projectsまたは検索結果が返した値をそのまま使う。"
            )
        ),
    ] = None,
    limit: Annotated[
        int,
        Field(
            description="返す検索チャンク数。通常は5。必要な根拠が不足するときだけ増やす。",
            ge=1,
            le=10,
        ),
    ] = 5,
):
    from kb_search_core import search_knowledge as search

    resolution = resolve_owner(owner)
    results = search(query, owner=resolution.owner, projects=projects, limit=limit)
    return {
        "status": "ok",
        **owner_scope_metadata(resolution),
        "results": results,
    }


@mcp.tool(
    description=(
        "登録済みKnowledge Projectを一覧表示します。ownerを明示すると共有Projectとそのownerの"
        "個人Projectを返します。ownerを省略した場合、対応クライアントから利用者情報が転送されて"
        "いれば現在の利用者をownerとして自動補完し、補完できなければ共有Projectだけを返します。"
        "プロジェクト名やproject_idが不明なとき、検索対象を選ぶ前に使用します。"
    )
)
def list_knowledge_projects(
    owner: Annotated[
        str | None,
        Field(
            description=(
                "対象とする個人Knowledgeのownerアカウント名。別ownerを明示する場合に指定する。"
                "省略時は、対応クライアントから転送された現在の利用者情報で自動補完する。"
                "補完できない場合は共有Projectだけを返し、その事実を結果のhintとフラグで返す。"
            )
        ),
    ] = None,
):
    from kb_search_core import list_knowledge_projects as list_projects

    resolution = resolve_owner(owner)
    projects = list_projects(owner=resolution.owner)
    return {
        "status": "ok",
        **owner_scope_metadata(resolution),
        "projects": projects,
    }


@mcp.tool(
    description=(
        "検索結果のチャンクだけでは前後関係や実装の詳細が不足する場合に限り、保存済み原本の"
        "テキストファイルを行範囲で参照します。最初から原本を広く読むのではなく、まず"
        "search_knowledgeで関連箇所を検索し、その結果に含まれるscope、project_name、owner、"
        "relative_pathを使って呼び出してください。personalを読む場合、ownerを省略すると対応"
        "クライアントから転送された現在の利用者情報で自動補完します。"
        "PDFや画像などの非テキスト形式には使用できません。必要な範囲だけを読み、続きが必要なら"
        "start_lineを進めて再度呼び出してください。"
    )
)
def read_knowledge_source(
    scope: Annotated[
        Literal["shared", "personal"],
        Field(
            description=(
                "原本の範囲。共有Projectは'shared'、個人Projectは'personal'を指定する。"
                "検索結果またはlist_knowledge_projectsが返したscopeをそのまま使う。"
            )
        ),
    ],
    project: Annotated[
        str,
        Field(
            description=(
                "人間向けのproject_name（保存フォルダ名）。project_idやCollection名ではなく、"
                "検索結果または一覧が返したproject_nameを正確に指定する。日本語・空白・記号を"
                "短縮、翻訳、要約せずそのまま保持する。"
            ),
            min_length=1,
        ),
    ],
    relative_path: Annotated[
        str,
        Field(
            description=(
                "Project原本内の相対ファイルパス。検索結果に含まれるrelative_pathをそのまま指定する。"
                "絶対パスやProject外を指すパスは指定しない。"
            ),
            min_length=1,
        ),
    ],
    owner: Annotated[
        str | None,
        Field(
            description=(
                "personal原本のownerアカウント名。検索結果が返したownerを指定できる。省略時は対応"
                "クライアントから転送された現在の利用者情報で自動補完する。scope='shared'では省略する。"
            )
        ),
    ] = None,
    start_line: Annotated[
        int,
        Field(
            description="読み始める1始まりの行番号。最初は1、続きを読むときは前回のend_line+1。",
            ge=1,
        ),
    ] = 1,
    max_lines: Annotated[
        int,
        Field(
            description="一度に読む最大行数。通常は必要最小限にし、最大400行。",
            ge=1,
            le=400,
        ),
    ] = 200,
):
    from kb_search_core import read_knowledge_source as read_source

    resolution = resolve_owner(owner) if scope == "personal" else None
    return read_source(
        scope=scope,
        owner=resolution.owner if resolution else None,
        project=project,
        relative_path=relative_path,
        start_line=start_line,
        max_lines=max_lines,
    )


def main() -> None:
    mcp.settings.host = os.environ.get("MCP_HOST", "0.0.0.0")
    mcp.settings.port = int(os.environ.get("MCP_PORT", "8000"))

    import uvicorn

    app = CaptureHttpHeadersMiddleware(mcp.streamable_http_app())
    uvicorn.run(app, host=mcp.settings.host, port=mcp.settings.port)


if __name__ == "__main__":
    main()
