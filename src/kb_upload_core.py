from __future__ import annotations

import os
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from kb_common import INCOMING_ROOT, resolve_under, sanitize_identifier
from kb_project_metadata import validate_project_name

UPLOAD_MAX_BYTES = int(os.environ.get("UPLOAD_MAX_BYTES", str(512 * 1024 * 1024)))
UPLOAD_MAX_EXTRACTED_BYTES = int(
    os.environ.get("UPLOAD_MAX_EXTRACTED_BYTES", str(2 * 1024 * 1024 * 1024))
)
UPLOAD_MAX_FILES = int(os.environ.get("UPLOAD_MAX_FILES", "20000"))


def _project_name(value: str) -> str:
    return validate_project_name(value)


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = info.external_attr >> 16
    return stat.S_ISLNK(mode)


def _safe_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = archive.infolist()
    if len(members) > UPLOAD_MAX_FILES:
        raise ValueError(f"ZIP内のファイル数が上限を超えています: {len(members)}")

    total_size = 0
    safe: list[zipfile.ZipInfo] = []
    for info in members:
        path = Path(info.filename.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"ZIP内に不正なパスがあります: {info.filename}")
        if _is_symlink(info):
            raise ValueError(f"ZIP内のシンボリックリンクは登録できません: {info.filename}")
        total_size += info.file_size
        if total_size > UPLOAD_MAX_EXTRACTED_BYTES:
            raise ValueError("ZIP展開後サイズが上限を超えています")
        safe.append(info)
    return safe


def _content_root(extracted_root: Path) -> Path:
    """単一のトップレベルディレクトリだけを含むZIPなら、その中身をproject直下に置く。"""
    entries = [path for path in extracted_root.iterdir() if path.name != "__MACOSX"]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return extracted_root


def upload_project_archive(
    archive_path: Path,
    owner: str,
    project: str,
    original_filename: str,
) -> dict[str, Any]:
    owner_id = sanitize_identifier(owner)
    project_name = _project_name(project)

    if not archive_path.is_file():
        raise FileNotFoundError("アップロードされたファイルが見つかりません")
    if archive_path.stat().st_size > UPLOAD_MAX_BYTES:
        raise ValueError("アップロードサイズが上限を超えています")
    if not zipfile.is_zipfile(archive_path):
        raise ValueError("ZIP形式のファイルを指定してください")

    destination = resolve_under(INCOMING_ROOT, "users", owner_id, project_name)
    if destination.exists():
        raise FileExistsError("incomingに同名projectが存在します。自動上書きは行いません")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="kb-upload-") as temp_dir:
        extracted = Path(temp_dir) / "extracted"
        extracted.mkdir()
        with zipfile.ZipFile(archive_path) as archive:
            members = _safe_members(archive)
            archive.extractall(extracted, members=members)

        source = _content_root(extracted)
        if not any(source.iterdir()):
            raise ValueError("ZIPに登録可能なファイルが含まれていません")

        try:
            shutil.copytree(source, destination)
        except Exception:
            shutil.rmtree(destination, ignore_errors=True)
            raise

    return {
        "status": "uploaded",
        "source_preserved": True,
        "owner": owner_id,
        "project": project_name,
        "filename": Path(original_filename).name,
        "incoming_path": str(destination),
    }
