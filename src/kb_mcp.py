from __future__ import annotations

import asyncio
import contextlib
import contextvars
import os
import shutil
import stat
import tempfile
import threading
import uuid
import zipfile
from pathlib import Path
from typing import Any

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from kb_index import index_directory, sanitize_identifier
from kb_search_core import (
    DEFAULT_SEARCH_LIMIT,
    list_knowledge_projects as list_projects_core,
    read_knowledge_source as read_source_core,
    search_knowledge as search_core,
)

KNOWLEDGE_ROOT = Path(os.environ.get("KNOWLEDGE_ROOT", "/knowledge")).expanduser()
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.environ.get("MCP_PORT", "8000"))
MAX_UPLOAD_BYTES = int(os.environ.get("KB_MAX_UPLOAD_BYTES", str(2 * 1024**3)))
MAX_EXTRACTED_BYTES = int(os.environ.get("KB_MAX_EXTRACTED_BYTES", str(5 * 1024**3)))
MAX_ARCHIVE_FILES = int(os.environ.get("KB_MAX_ARCHIVE_FILES", "100000"))

# Initial version intentionally allows only one registration at a time.
_INDEX_LOCK = threading.Lock()
_REQUEST_OWNER: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "knowledge_request_owner", default=None
)


class ForwardedOwnerMiddleware:
    """Capture an owner hint forwarded by Open WebUI or another trusted client.

    This is identification, not authentication. The initial release is intended for
    trusted/internal deployments. A future version can replace this boundary with
    signed headers or authenticated user mapping without changing the tool logic.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("utf-8", errors="replace")
            for key, value in scope.get("headers", [])
        }
        forwarded = headers.get("x-knowledge-owner") or headers.get("x-openwebui-user-name")
        token = _REQUEST_OWNER.set(forwarded)
        try:
            await self.app(scope, receive, send)
        finally:
            _REQUEST_OWNER.reset(token)



def _validate_project_name(project: str) -> str:
    project_name = project.strip()
    if not project_name or Path(project_name).name != project_name:
        raise ValueError("projectには個人Knowledge領域直下のフォルダ名を指定してください")
    return project_name


def _validate_zip_members(archive: zipfile.ZipFile) -> None:
    total_size = 0
    members = archive.infolist()
    if len(members) > MAX_ARCHIVE_FILES:
        raise ValueError(f"ZIP内のファイル数が上限を超えています: {len(members)}")

    for member in members:
        member_path = Path(member.filename)
        if member_path.is_absolute() or ".." in member_path.parts:
            raise ValueError(f"安全でないZIP内パスです: {member.filename}")
        mode = member.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise ValueError(f"ZIP内のシンボリックリンクは登録できません: {member.filename}")
        total_size += member.file_size
        if total_size > MAX_EXTRACTED_BYTES:
            raise ValueError("ZIPの展開後サイズが上限を超えています")


def _archive_payload_root(extracted_dir: Path) -> Path:
    entries = [entry for entry in extracted_dir.iterdir() if entry.name != "__MACOSX"]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return extracted_dir


def _save_upload(upload, destination: Path) -> int:
    written = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as output:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                raise ValueError("アップロードサイズが上限を超えています")
            output.write(chunk)
    return written


def _install_uploaded_project(
    upload,
    owner_id: str,
    project_name: str,
    project_id: str | None,
) -> dict[str, Any]:
    if not upload.filename or not upload.filename.lower().endswith(".zip"):
        raise ValueError("登録ファイルはZIP形式にしてください")

    user_root = (KNOWLEDGE_ROOT / "users" / owner_id).resolve()
    source_path = (user_root / project_name).resolve()
    if not source_path.is_relative_to(user_root):
        raise ValueError("個人Knowledge領域外のパスは登録できません")
    if source_path.exists():
        raise FileExistsError(
            f"同名の原本がすでに存在します。既存原本は自動的に上書きしません: {source_path}"
        )

    upload_root = KNOWLEDGE_ROOT / "uploads" / "users" / owner_id
    saved_zip = upload_root / f"{uuid.uuid4().hex}_{Path(upload.filename).name}"
    _save_upload(upload, saved_zip)

    user_root.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(tempfile.mkdtemp(prefix=f".{project_name}-", dir=user_root))
    try:
        with zipfile.ZipFile(saved_zip) as archive:
            _validate_zip_members(archive)
            archive.extractall(staging_dir)

        payload_root = _archive_payload_root(staging_dir)
        if payload_root == staging_dir:
            final_staging = staging_dir
        else:
            final_staging = payload_root

        if source_path.exists():
            raise FileExistsError(
                f"同名の原本がすでに存在します。既存原本は自動的に上書きしません: {source_path}"
            )
        final_staging.rename(source_path)
        if staging_dir.exists() and staging_dir != source_path:
            shutil.rmtree(staging_dir, ignore_errors=True)

        result = index_directory(
            source_path,
            shared=False,
            owner=owner_id,
            project_id=project_id or sanitize_identifier(project_name),
        )
        return {
            "status": "completed",
            "owner": owner_id,
            "project": project_name,
            "source_path": str(source_path),
            "uploaded_zip": str(saved_zip),
            "index": result,
        }
    except Exception:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        raise


async def upload_project(request: Request) -> JSONResponse:
    try:
        owner_id = resolve_owner()
        form = await request.form()
        project_name = _validate_project_name(str(form.get("project") or ""))
        project_id_value = str(form.get("project_id") or "").strip() or None
        upload = form.get("file")
        if upload is None or not hasattr(upload, "file"):
            return JSONResponse({"status": "error", "message": "fileが必要です"}, status_code=400)

        if not _INDEX_LOCK.acquire(blocking=False):
            return JSONResponse(
                {
                    "status": "busy",
                    "message": "別のナレッジを登録中です。しばらくしてから再度実行してください。",
                },
                status_code=409,
            )
        try:
            result = await asyncio.to_thread(
                _install_uploaded_project, upload, owner_id, project_name, project_id_value
            )
            return JSONResponse(result, status_code=201)
        finally:
            _INDEX_LOCK.release()
    except FileExistsError as exc:
        return JSONResponse({"status": "conflict", "message": str(exc)}, status_code=409)
    except (ValueError, zipfile.BadZipFile) as exc:
        return JSONResponse({"status": "error", "message": str(exc)}, status_code=400)
    except ToolError as exc:
        return JSONResponse({"status": "error", "message": str(exc)}, status_code=401)
    except Exception as exc:
        return JSONResponse(
            {
                "status": "index_failed",
                "message": f"登録に失敗しました。保存済みの原本とZIPは自動削除しません: {exc}",
            },
            status_code=500,
        )

def resolve_owner(explicit_owner: str | None = None) -> str:
    value = explicit_owner or _REQUEST_OWNER.get()
    if not value:
        raise ToolError(
            "ユーザー名を特定できません。Open WebUIのユーザー情報ヘッダー転送を有効にするか、"
            "エージェント接続でX-Knowledge-Ownerを設定してください。"
        )
    return sanitize_identifier(value)


mcp = FastMCP(
    "filesystem-knowledge-bridge",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
)


@mcp.tool()
def search_knowledge(
    query: str,
    projects: list[str] | None = None,
    limit: int = DEFAULT_SEARCH_LIMIT,
    owner: str | None = None,
) -> list[dict[str, Any]]:
    """Search shared Knowledge and the current user's personal Knowledge.

    Specify projects when the current conversation or agent instruction identifies
    the relevant project. Omit projects only when discovering related projects or
    searching across all accessible Knowledge. The final result count is global,
    not per collection.

    owner is normally inferred from a forwarded request header. The optional owner
    argument exists only as a fallback for trusted clients in the initial version.
    """
    try:
        resolved_owner = resolve_owner(owner)
        return [item.to_dict() for item in search_core(query, resolved_owner, projects, limit)]
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
def list_knowledge_projects(owner: str | None = None) -> list[dict[str, Any]]:
    """List shared projects and the current user's personal projects.

    Use only when the user explicitly asks for a list or a project name cannot be
    determined by normal Knowledge search.
    """
    try:
        return list_projects_core(resolve_owner(owner))
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
def read_knowledge_source(
    source_ref: str,
    start_line: int = 1,
    max_lines: int = 200,
    owner: str | None = None,
) -> dict[str, Any]:
    """Read a limited range from an original text/source file found by search.

    Use this cautiously and only when search chunks do not provide enough context,
    such as when source-code imports, callers, surrounding functions, or complete
    configuration structure must be checked. Pass logical_path from a search result
    as source_ref. Binary documents are intentionally unsupported in the initial version.
    """
    try:
        return read_source_core(source_ref, resolve_owner(owner), start_line, max_lines)
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
def index_personal_knowledge(
    project: str,
    project_id: str | None = None,
    owner: str | None = None,
) -> dict[str, Any]:
    """Index a pre-positioned frozen project as the current user's personal Knowledge.

    The source must already exist at /knowledge/users/<owner>/<project>. This tool
    never creates, overwrites, moves, or deletes original files. If another index
    operation is running, it immediately returns a busy error; retry later.
    """
    owner_id = resolve_owner(owner)
    try:
        project_dir_name = _validate_project_name(project)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc

    source_root = (KNOWLEDGE_ROOT / "users" / owner_id).resolve()
    source_path = (source_root / project_dir_name).resolve()
    if not source_path.is_relative_to(source_root):
        raise ToolError("個人Knowledge領域外のパスは登録できません")
    if not source_path.is_dir():
        raise ToolError(f"配置済みプロジェクトが見つかりません: {source_path}")

    if not _INDEX_LOCK.acquire(blocking=False):
        raise ToolError("別のナレッジを登録中です。しばらくしてから再度実行してください。")

    try:
        return index_directory(
            source_path,
            shared=False,
            owner=owner_id,
            project_id=project_id or sanitize_identifier(project_dir_name),
        )
    except Exception as exc:
        raise ToolError(
            f"登録に失敗しました。原本は変更されていません。再度登録してください: {exc}"
        ) from exc
    finally:
        _INDEX_LOCK.release()


@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    async with mcp.session_manager.run():
        yield


app = ForwardedOwnerMiddleware(
    Starlette(
        routes=[
            Route("/api/projects/upload", upload_project, methods=["POST"]),
            Mount("/mcp", app=mcp.streamable_http_app()),
        ],
        lifespan=lifespan,
    )
)


def main() -> None:
    uvicorn.run(app, host=MCP_HOST, port=MCP_PORT)


if __name__ == "__main__":
    main()
