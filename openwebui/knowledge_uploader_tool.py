"""
title: Knowledge Project Uploader
author: filesystem-knowledge-bridge
version: 0.1.0
required_open_webui_version: 0.10.0
requirements: httpx>=0.27
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import httpx
from pydantic import BaseModel, Field


class Tools:
    """Open WebUIの添付ZIPをknowledge-upload-apiへ転送するTool。登録処理は行わない。"""

    class Valves(BaseModel):
        upload_api_url: str = Field(
            default="http://knowledge-upload-api:8002",
            description="filesystem-knowledge-bridge uploader APIのURL",
        )
        uploads_root: str = Field(
            default="/app/backend/data/uploads",
            description="Open WebUIコンテナ内のアップロード保存ディレクトリ",
        )
        timeout_seconds: int = Field(default=300, ge=1, le=3600)

    def __init__(self) -> None:
        self.valves = self.Valves()

    @staticmethod
    def _file_record(item: dict[str, Any]) -> dict[str, Any]:
        record = item.get("file") or item.get("files")
        if not isinstance(record, dict):
            raise ValueError("添付ファイル情報を取得できません")
        return record

    @staticmethod
    def _owner(__user__: dict[str, Any] | None) -> str:
        if not __user__:
            raise ValueError("Open WebUIのユーザー情報を取得できません")
        name = str(__user__.get("name") or "").strip()
        if name:
            return name
        email = str(__user__.get("email") or "").strip()
        if email and "@" in email:
            return email.split("@", 1)[0]
        raise ValueError("ownerへ変換できるユーザー情報がありません")

    def _path(self, record: dict[str, Any]) -> Path:
        file_id = str(record.get("id") or "")
        filename = str(record.get("filename") or "")
        if not file_id or not filename:
            raise ValueError("添付ファイルのIDまたはファイル名がありません")
        path = Path(self.valves.uploads_root) / f"{file_id}_{Path(filename).name}"
        if not path.is_file():
            raise FileNotFoundError(f"添付ファイルの実体が見つかりません: {path}")
        return path

    async def upload_project(
        self,
        project: Annotated[
            str,
            (
                "ユーザーが指定したproject名を一字一句変更せず渡してください。"
                "日本語、空白、アンダースコア、ハイフンを保持し、短縮・要約・翻訳しないでください。"
                "未指定の場合だけ空文字列を渡してください。"
            ),
        ] = "",
        __files__: list[dict[str, Any]] | None = None,
        __user__: dict[str, Any] | None = None,
        __event_emitter__=None,
    ) -> str:
        """添付された1個のZIPをincomingへアップロードします。

        このToolはアップロードと展開だけを行い、登録・インデックス作成は行いません。
        添付ファイルがない場合は呼び出さないでください。
        成功後は、同じownerとprojectを使ってRegister MCPの
        register_incoming_projectを呼び出してください。
        projectを省略した場合はZIPファイル名から推定します。
        """
        files = __files__ or []
        if len(files) != 1:
            raise ValueError("ZIPファイルを1個だけ添付してください")

        record = self._file_record(files[0])
        filename = str(record.get("filename") or "")
        if not filename.lower().endswith(".zip"):
            raise ValueError("ZIPファイルを添付してください")

        project_name = project.strip() or Path(filename).stem
        owner = self._owner(__user__)
        file_path = self._path(record)

        if __event_emitter__:
            await __event_emitter__({
                "type": "status",
                "data": {"description": "ZIPをincomingへアップロードしています...", "done": False},
            })

        async with httpx.AsyncClient(timeout=self.valves.timeout_seconds) as client:
            with file_path.open("rb") as source:
                response = await client.post(
                    f"{self.valves.upload_api_url.rstrip('/')}/uploads/projects",
                    data={"owner": owner, "project": project_name},
                    files={"archive": (filename, source, "application/zip")},
                )

        if response.is_error:
            detail = response.text
            try:
                detail = response.json().get("detail", detail)
            except Exception:
                pass
            raise RuntimeError(f"アップロードに失敗しました ({response.status_code}): {detail}")

        result = response.json()
        if __event_emitter__:
            await __event_emitter__({
                "type": "status",
                "data": {"description": "incomingへのアップロードが完了しました", "done": True},
            })
        return (
            f"アップロード完了: owner={result['owner']}, project={result['project']}, "
            f"incoming_path={result['incoming_path']}。"
            "続けてRegister MCPのregister_incoming_projectを同じowner/projectで呼び出してください。"
        )
