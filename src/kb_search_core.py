from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from qdrant_client import QdrantClient

from kb_common import (
    EMBEDDING_MODEL,
    KNOWLEDGE_ROOT,
    LITELLM_API_BASE,
    LITELLM_API_KEY,
    QDRANT_API_KEY,
    QDRANT_URL,
    resolve_under,
    sanitize_identifier,
)

TEXT_SOURCE_EXTENSIONS = {
    ".txt", ".rst", ".yaml", ".yml", ".json", ".csv", ".toml", ".ini", ".cfg", ".tex",
    ".md", ".markdown", ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".c", ".h",
    ".cpp", ".cc", ".cxx", ".hpp", ".cs", ".go", ".rs", ".rb", ".php",
}


def embed_query(query: str) -> list[float]:
    if not LITELLM_API_KEY:
        raise RuntimeError("LITELLM_API_KEYが未設定です")
    response = httpx.post(
        f"{LITELLM_API_BASE}/embeddings",
        headers={"Authorization": f"Bearer {LITELLM_API_KEY}"},
        json={"model": EMBEDDING_MODEL, "input": query, "encoding_format": "float"},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["data"][0]["embedding"]


def list_allowed_collections(client: QdrantClient, owner: str | None) -> list[str]:
    names = [item.name for item in client.get_collections().collections]
    allowed = [name for name in names if name.startswith("shared_")]
    if owner:
        prefix = f"private_{sanitize_identifier(owner)}_"
        allowed.extend(name for name in names if name.startswith(prefix))
    return sorted(set(allowed))


def filter_projects(
    client: QdrantClient,
    collections: list[str],
    projects: list[str] | None,
) -> list[str]:
    if not projects:
        return collections
    requested = {project.strip() for project in projects if project.strip()}
    if not requested:
        return collections
    return [
        collection
        for collection in collections
        if _project_matches(_collection_project_info(client, collection), requested)
    ]


def _metadata_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        return metadata
    node_content = payload.get("_node_content")
    if isinstance(node_content, str):
        try:
            parsed = json.loads(node_content)
            value = parsed.get("metadata")
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass
    return payload


def _text_from_payload(payload: dict[str, Any]) -> str:
    value = payload.get("text")
    if isinstance(value, str):
        return value
    metadata = payload.get("metadata")
    if isinstance(metadata, dict) and isinstance(metadata.get("text"), str):
        return metadata["text"]
    node_content = payload.get("_node_content")
    if isinstance(node_content, str):
        try:
            parsed = json.loads(node_content)
            for key in ("text", "text_resource"):
                candidate = parsed.get(key)
                if isinstance(candidate, str):
                    return candidate
                if isinstance(candidate, dict) and isinstance(candidate.get("text"), str):
                    return candidate["text"]
        except json.JSONDecodeError:
            pass
    return ""


def _collection_project_info(client: QdrantClient, collection: str) -> dict[str, str]:
    """Collection内のmetadataから人間向けproject名と内部IDを取得する。"""
    project_id = ""
    project_name = ""
    metadata_owner = ""
    metadata_scope = ""
    try:
        points, _ = client.scroll(
            collection_name=collection,
            limit=1,
            with_payload=True,
            with_vectors=False,
        )
        if points:
            metadata = _metadata_from_payload(points[0].payload or {})
            project_id = str(metadata.get("project_id") or "")
            project_name = str(metadata.get("project_name") or "")
            metadata_owner = str(metadata.get("owner") or "")
            metadata_scope = str(metadata.get("scope") or "")
    except Exception:
        # 一覧取得時は壊れたCollectionが1件あっても全体を止めない。
        pass

    if collection.startswith("shared_"):
        scope = "shared"
        owner = "shared"
        fallback_id = collection.removeprefix("shared_")
    else:
        scope = "personal"
        remainder = collection.removeprefix("private_")
        owner, _, fallback_id = remainder.partition("_")

    return {
        "scope": metadata_scope or scope,
        "owner": metadata_owner or owner,
        "project_id": project_id or fallback_id,
        "project_name": project_name or project_id or fallback_id,
        "collection": collection,
    }


def _project_matches(info: dict[str, str], requested: set[str]) -> bool:
    return info["project_id"] in requested or info["project_name"] in requested


def search_knowledge(
    query: str,
    *,
    owner: str | None = None,
    projects: list[str] | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    if not query.strip():
        raise ValueError("queryが空です")
    limit = max(1, min(limit, 10))
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    collections = filter_projects(client, list_allowed_collections(client, owner), projects)
    if not collections:
        return []

    vector = embed_query(query)
    candidates: list[dict[str, Any]] = []
    per_collection = min(max(limit, 3), 10)
    for collection in collections:
        result = client.query_points(
            collection_name=collection,
            query=vector,
            limit=per_collection,
            with_payload=True,
            with_vectors=False,
        )
        for point in result.points:
            payload = point.payload or {}
            metadata = _metadata_from_payload(payload)
            candidates.append({
                "score": float(point.score),
                "collection": collection,
                "text": _text_from_payload(payload),
                "scope": metadata.get("scope"),
                "owner": metadata.get("owner"),
                "project_id": metadata.get("project_id"),
                "project_name": metadata.get("project_name"),
                "relative_path": metadata.get("relative_path"),
                "logical_path": metadata.get("logical_path"),
                "chunk_index": metadata.get("chunk_index"),
                "logical_id": metadata.get("logical_id"),
            })
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates[:limit]


def list_knowledge_projects(owner: str | None = None) -> list[dict[str, str]]:
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    return [
        _collection_project_info(client, collection)
        for collection in list_allowed_collections(client, owner)
    ]


def read_knowledge_source(
    *,
    scope: str,
    project: str,
    relative_path: str,
    owner: str | None = None,
    start_line: int = 1,
    max_lines: int = 200,
) -> dict[str, Any]:
    project_name = Path(project).name
    if project_name != project or project in {"", ".", ".."}:
        raise ValueError("不正なproject名です")
    if scope == "shared":
        root = resolve_under(KNOWLEDGE_ROOT, "shared", project_name)
    elif scope == "personal":
        if not owner:
            raise ValueError("個人ナレッジの参照にはownerが必要です")
        root = resolve_under(KNOWLEDGE_ROOT, "users", sanitize_identifier(owner), project_name)
    else:
        raise ValueError("scopeはsharedまたはpersonalです")

    target = resolve_under(root, relative_path)
    if not target.is_file():
        raise FileNotFoundError(f"原本が見つかりません: {relative_path}")
    if target.suffix.lower() not in TEXT_SOURCE_EXTENSIONS:
        raise ValueError("この形式は原本テキスト参照の対象外です")

    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(1, start_line)
    count = max(1, min(max_lines, 400))
    selected = lines[start - 1:start - 1 + count]
    return {
        "scope": scope,
        "owner": "shared" if scope == "shared" else sanitize_identifier(owner or ""),
        "project": project_name,
        "relative_path": relative_path,
        "start_line": start,
        "end_line": start + len(selected) - 1,
        "total_lines": len(lines),
        "content": "\n".join(f"{number}: {line}" for number, line in enumerate(selected, start=start)),
    }
