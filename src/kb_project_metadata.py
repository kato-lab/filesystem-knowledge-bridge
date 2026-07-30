from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

PROJECT_METADATA_FILENAME = ".kb_project.json"


def validate_project_name(value: str) -> str:
    """ユーザー向けproject名を壊さず、安全な単一ディレクトリ名として検証する。"""
    name = value.strip()
    if not name or name in {".", ".."}:
        raise ValueError("不正なproject名です")
    if "/" in name or "\\" in name:
        raise ValueError("project名にパス区切り文字は使用できません")
    if "\x00" in name:
        raise ValueError("project名にNUL文字は使用できません")
    return name


def normalize_project_id(value: str | None) -> str:
    """指定値をUUIDとして正規化し、未指定ならUUIDv4を生成する。"""
    if value is None or not value.strip():
        return str(uuid4())
    try:
        return str(UUID(value.strip()))
    except ValueError as exc:
        raise ValueError("project_idにはUUIDを指定してください") from exc


def metadata_path(project_root: Path) -> Path:
    return project_root / PROJECT_METADATA_FILENAME


def read_project_metadata(project_root: Path) -> dict[str, Any] | None:
    path = metadata_path(project_root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"project metadataを読み込めません: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"project metadataの形式が不正です: {path}")
    return data


def write_project_metadata(
    project_root: Path,
    *,
    project: str,
    project_id: str,
    owner: str,
    scope: str,
) -> dict[str, str]:
    data = {
        "project": validate_project_name(project),
        "project_id": normalize_project_id(project_id),
        "owner": owner,
        "scope": scope,
    }
    path = metadata_path(project_root)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)
    return data
