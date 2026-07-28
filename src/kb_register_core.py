from __future__ import annotations

import shutil
import threading
from pathlib import Path
from typing import Any

from kb_common import INCOMING_ROOT, KNOWLEDGE_ROOT, resolve_under, sanitize_identifier

_REGISTER_LOCK = threading.Lock()


def _project_name(value: str) -> str:
    name = Path(value).name
    if name != value or value in {"", ".", ".."}:
        raise ValueError("不正なproject名です")
    return name


def list_incoming(owner: str) -> list[str]:
    owner_id = sanitize_identifier(owner)
    root = resolve_under(INCOMING_ROOT, "users", owner_id)
    if not root.is_dir():
        return []
    return sorted(path.name for path in root.iterdir() if path.is_dir() and not path.name.startswith("."))


def register_incoming_project(owner: str, project: str, project_id: str | None = None) -> dict[str, Any]:
    owner_id = sanitize_identifier(owner)
    project_name = _project_name(project)
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
        from kb_index import index_directory

        result = index_directory(destination, owner=owner_id, project_id=project_id)
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
        from kb_index import index_directory

        result = index_directory(source, owner=owner_id, project_id=project_id)
        return {"status": "completed", "source_preserved": True, **result}
    finally:
        _REGISTER_LOCK.release()
