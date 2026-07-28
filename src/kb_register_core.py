from __future__ import annotations

import shutil
import threading
from pathlib import Path
from typing import Any

from kb_common import INCOMING_ROOT, KNOWLEDGE_ROOT, sanitize_identifier
from kb_index import index_directory

_REGISTER_LOCK = threading.Lock()


def list_incoming_projects(owner: str) -> list[str]:
    owner_id = sanitize_identifier(owner)
    root = (INCOMING_ROOT / "users" / owner_id).resolve()
    if not root.is_dir():
        return []
    return sorted(path.name for path in root.iterdir() if path.is_dir() and not path.name.startswith("."))


def import_incoming_project(owner: str, project: str, project_id: str | None = None) -> dict[str, Any]:
    """Copy an incoming directory to the protected source store and index it.

    Incoming and existing source directories are never deleted or overwritten.
    A failed index can be retried with index_stored_project().
    """
    owner_id = sanitize_identifier(owner)
    project_dir = project.strip()
    if not project_dir or Path(project_dir).name != project_dir:
        raise ValueError("projectにはincoming直下のフォルダ名を指定してください")

    incoming_root = (INCOMING_ROOT / "users" / owner_id).resolve()
    source = (incoming_root / project_dir).resolve()
    if not source.is_relative_to(incoming_root) or not source.is_dir():
        raise FileNotFoundError(f"incomingプロジェクトが見つかりません: {source}")

    knowledge_root = (KNOWLEDGE_ROOT / "users" / owner_id).resolve()
    destination = (knowledge_root / project_dir).resolve()
    if not destination.is_relative_to(knowledge_root):
        raise PermissionError("個人Knowledge領域外へ配置できません")

    if not _REGISTER_LOCK.acquire(blocking=False):
        raise RuntimeError("別のナレッジを登録中です。しばらくしてから再度実行してください。")
    try:
        if destination.exists():
            raise FileExistsError(
                f"保存済み原本が存在します。自動上書きしません: {destination}. "
                "Qdrantだけ再構築する場合はindex_stored_projectを使用してください。"
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination)
        result = index_directory(
            destination,
            shared=False,
            owner=owner_id,
            project_id=project_id or sanitize_identifier(project_dir),
        )
        return {"source": str(destination), "incoming_preserved": True, **result}
    finally:
        _REGISTER_LOCK.release()


def index_stored_project(owner: str, project: str, project_id: str | None = None) -> dict[str, Any]:
    """Rebuild Qdrant from an already stored original without modifying files."""
    owner_id = sanitize_identifier(owner)
    project_dir = project.strip()
    if not project_dir or Path(project_dir).name != project_dir:
        raise ValueError("projectには個人Knowledge領域直下のフォルダ名を指定してください")

    root = (KNOWLEDGE_ROOT / "users" / owner_id).resolve()
    source = (root / project_dir).resolve()
    if not source.is_relative_to(root) or not source.is_dir():
        raise FileNotFoundError(f"保存済み原本が見つかりません: {source}")

    if not _REGISTER_LOCK.acquire(blocking=False):
        raise RuntimeError("別のナレッジを登録中です。しばらくしてから再度実行してください。")
    try:
        return index_directory(
            source,
            shared=False,
            owner=owner_id,
            project_id=project_id or sanitize_identifier(project_dir),
        )
    finally:
        _REGISTER_LOCK.release()
