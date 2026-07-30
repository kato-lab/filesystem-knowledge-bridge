from __future__ import annotations

import shutil
import threading
from pathlib import Path
from typing import Any

from kb_common import INCOMING_ROOT, KNOWLEDGE_ROOT, resolve_under, sanitize_identifier
from kb_project_metadata import (
    normalize_project_id,
    read_project_metadata,
    validate_project_name,
    write_project_metadata,
)

_REGISTER_LOCK = threading.Lock()


def _project_name(value: str) -> str:
    return validate_project_name(value)


def list_incoming(owner: str) -> list[str]:
    owner_id = sanitize_identifier(owner)
    root = resolve_under(INCOMING_ROOT, "users", owner_id)
    if not root.is_dir():
        return []
    return sorted(path.name for path in root.iterdir() if path.is_dir() and not path.name.startswith("."))


def register_incoming_project(owner: str, project: str, project_id: str | None = None) -> dict[str, Any]:
    owner_id = sanitize_identifier(owner)
    project_name = _project_name(project)
    normalized_project_id = normalize_project_id(project_id)
    source = resolve_under(INCOMING_ROOT, "users", owner_id, project_name)
    destination = resolve_under(KNOWLEDGE_ROOT, "users", owner_id, project_name)
    if not source.is_dir():
        raise FileNotFoundError(f"incoming projectが見つかりません: {project_name}")
    if destination.exists():
        raise FileExistsError("保存済み原本が存在します。自動上書きは行いません")
    if not _REGISTER_LOCK.acquire(blocking=False):
        raise RuntimeError("別のナレッジを登録中です。しばらくしてから再度実行してください")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination)
        write_project_metadata(
            destination,
            project=project_name,
            project_id=normalized_project_id,
            owner=owner_id,
            scope="personal",
        )

        from kb_index import index_directory

        result = index_directory(
            destination,
            owner=owner_id,
            project_id=normalized_project_id,
            project_name=project_name,
        )
        return {"status": "completed", "source_preserved": True, "stored_path": str(destination), **result}
    finally:
        _REGISTER_LOCK.release()


def reindex_stored_project(owner: str, project: str, project_id: str | None = None) -> dict[str, Any]:
    owner_id = sanitize_identifier(owner)
    project_name = _project_name(project)
    source = resolve_under(KNOWLEDGE_ROOT, "users", owner_id, project_name)
    if not source.is_dir():
        raise FileNotFoundError(f"保存済みprojectが見つかりません: {project_name}")
    if not _REGISTER_LOCK.acquire(blocking=False):
        raise RuntimeError("別のナレッジを登録中です。しばらくしてから再度実行してください")
    try:
        metadata = read_project_metadata(source)
        if metadata:
            raw_project_id = str(metadata.get("project_id") or "").strip()
            if not raw_project_id:
                raise ValueError("保存済みproject metadataにproject_idがありません")
            stored_project_id = normalize_project_id(raw_project_id)
            if project_id is not None and normalize_project_id(project_id) != stored_project_id:
                raise ValueError("指定されたproject_idが保存済みmetadataと一致しません")
            normalized_project_id = stored_project_id
            stored_project_name = validate_project_name(str(metadata.get("project") or project_name))
        else:
            # 旧形式の保存済みprojectは、最初の再インデックス時にUUIDを付与する。
            normalized_project_id = normalize_project_id(project_id)
            stored_project_name = project_name
            write_project_metadata(
                source,
                project=stored_project_name,
                project_id=normalized_project_id,
                owner=owner_id,
                scope="personal",
            )

        from kb_index import index_directory

        result = index_directory(
            source,
            owner=owner_id,
            project_id=normalized_project_id,
            project_name=stored_project_name,
        )
        return {"status": "completed", "source_preserved": True, **result}
    finally:
        _REGISTER_LOCK.release()
