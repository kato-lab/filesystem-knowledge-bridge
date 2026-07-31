from __future__ import annotations

import os
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from kb_common import create_transport_security

mcp = FastMCP(
    "filesystem-knowledge-bridge register",
    json_response=True,
    transport_security=create_transport_security(8001),
)


@mcp.tool(
    description=(
        "incoming/users/<owner>に配置されている未登録の候補Projectを一覧表示します。現在の利用者の"
        "アカウント名をownerに指定してください。登録したいProject名が不明な場合や、手動配置・"
        "アップロードが成功したか確認するときに、register_incoming_projectより先に使用します。"
        "返されたProject名は短縮、翻訳、要約せず、そのままregister_incoming_projectのprojectへ"
        "渡してください。"
    )
)
def list_incoming(
    owner: Annotated[
        str,
        Field(
            description=(
                "現在の利用者に対応するKnowledge ownerのアカウント名。Open WebUI等の利用者情報から"
                "得た値を指定する。メールアドレスや表示用氏名へ勝手に変換しない。値が不明なら"
                "利用者へ確認する。"
            ),
            min_length=1,
        ),
    ],
):
    from kb_register_core import list_incoming as list_projects

    return list_projects(owner)


@mcp.tool(
    description=(
        "incomingに既に配置されている個人Projectを保存済み原本領域へコピーし、Qdrantへ新規登録します。"
        "添付ファイルをUploaderで配置した場合は、Uploaderの成功後に同じownerとprojectで呼び出して"
        "ください。添付がなく、利用者がincoming上のProject名を指定した場合は直接呼び出せます。"
        "projectには利用者が指定した名前またはlist_incomingの結果を一字一句そのまま渡し、短縮、翻訳、"
        "要約、キーワード抽出をしないでください。project_idは内部識別子であり通常は必ず省略します。"
        "省略時はRegister側がUUIDv4を生成します。保存済み原本が既に存在する場合は上書きせず失敗します。"
    )
)
def register_incoming_project(
    owner: Annotated[
        str,
        Field(
            description=(
                "登録先となるKnowledge ownerのアカウント名。現在の利用者に対応する値を指定し、"
                "Uploaderを使った場合はUploader結果のownerと完全に同じ値を使う。"
            ),
            min_length=1,
        ),
    ],
    project: Annotated[
        str,
        Field(
            description=(
                "incoming内の人間向けProject名（フォルダ名）。利用者の指定、Uploader結果、または"
                "list_incomingの結果を一字一句そのまま使う。日本語、空白、アンダースコア、ハイフン等を"
                "短縮、翻訳、要約、正規化しない。"
            ),
            min_length=1,
        ),
    ],
    project_id: Annotated[
        str | None,
        Field(
            description=(
                "内部識別用UUID。通常の新規登録では必ず省略し、Register側にUUIDv4を生成させる。"
                "既存IDを維持する移行・復旧など、利用者または管理者が明示的なUUIDを指定した場合だけ"
                "渡す。Project名をproject_idへ変換してはならない。"
            )
        ),
    ] = None,
):
    from kb_register_core import register_incoming_project as register

    return register(owner, project, project_id)


@mcp.tool(
    description=(
        "保存済み原本からQdrant Collectionを削除・再構築します。原本の内容は変更しません。"
        "新規登録には使わず、インデックスの破損、Embedding設定変更、または明示的な再構築依頼のときに"
        "使用してください。projectには保存済み原本の人間向けProject名を正確に指定します。"
        "project_idは通常必ず省略し、保存済み.kb_project.jsonのUUIDを再利用させてください。"
        "利用者が明示した場合を除き、新しいUUIDを作成したりProject名をproject_idとして渡したり"
        "してはなりません。"
    )
)
def reindex_stored_project(
    owner: Annotated[
        str,
        Field(
            description=(
                "保存済みProjectを所有するKnowledge ownerのアカウント名。現在の利用者または"
                "対象Projectのownerを正確に指定する。"
            ),
            min_length=1,
        ),
    ],
    project: Annotated[
        str,
        Field(
            description=(
                "保存済み原本の人間向けProject名（フォルダ名）。list_knowledge_projects等が返した"
                "project_nameを一字一句そのまま指定し、project_idやCollection名は渡さない。"
            ),
            min_length=1,
        ),
    ],
    project_id: Annotated[
        str | None,
        Field(
            description=(
                "保存済みProjectの内部UUID。通常は必ず省略し、.kb_project.jsonに保存されたUUIDを"
                "再利用させる。旧形式Projectの初回移行など、管理者がUUIDを明示した場合だけ指定する。"
            )
        ),
    ] = None,
):
    from kb_register_core import reindex_stored_project as reindex

    return reindex(owner, project, project_id)


def main() -> None:
    mcp.settings.host = os.environ.get("MCP_HOST", "0.0.0.0")
    mcp.settings.port = int(os.environ.get("MCP_PORT", "8001"))
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
