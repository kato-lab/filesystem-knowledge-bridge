from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlparse

import httpx
from qdrant_client import QdrantClient

from kb_common import (
    EMBEDDING_MODEL,
    KNOWLEDGE_LOGICAL_ROOT,
    KNOWLEDGE_ROOT,
    LITELLM_API_BASE,
    LITELLM_API_KEY,
    QDRANT_API_KEY,
    QDRANT_URL,
    sanitize_identifier,
)

DEFAULT_SEARCH_LIMIT = int(os.environ.get("KB_SEARCH_LIMIT", "5"))
MAX_SEARCH_LIMIT = int(os.environ.get("KB_SEARCH_MAX_LIMIT", "10"))
MAX_SOURCE_LINES = int(os.environ.get("KB_SOURCE_MAX_LINES", "400"))

READABLE_EXTENSIONS = {
    ".md", ".markdown", ".txt", ".rst", ".yaml", ".yml", ".json", ".csv",
    ".toml", ".ini", ".cfg", ".tex", ".py", ".js", ".jsx", ".ts", ".tsx",
    ".java", ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".cs", ".go",
    ".rs", ".rb", ".php",
}


@dataclass(slots=True)
class SearchResult:
    score: float
    collection: str
    project_id: str
    project_name: str
    scope: str
    owner: str
    relative_path: str
    logical_path: str
    source_ref: str
    chunk_index: int
    text: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_qdrant_client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)


def embed_query(query: str) -> list[float]:
    if not LITELLM_API_KEY:
        raise RuntimeError("LITELLM_API_KEYが未設定です")
    response = httpx.post(
        f"{LITELLM_API_BASE}/embeddings",
        headers={"Authorization": f"Bearer {LITELLM_API_KEY}"},
        json={"model": EMBEDDING_MODEL, "input": query, "encoding_format": "float"},
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["data"][0]["embedding"]


def _collection_names(client: QdrantClient) -> list[str]:
    return sorted(item.name for item in client.get_collections().collections)


def accessible_collections(client: QdrantClient, owner: str) -> list[str]:
    owner_id = sanitize_identifier(owner)
    personal_prefix = f"private_{owner_id}_"
    return [
        name for name in _collection_names(client)
        if name.startswith("shared_") or name.startswith(personal_prefix)
    ]


def resolve_collections(client: QdrantClient, owner: str, projects: Iterable[str] | None = None) -> list[str]:
    allowed = accessible_collections(client, owner)
    requested = [sanitize_identifier(p) for p in (projects or []) if p and p.strip()]
    if not requested:
        return allowed

    selected = [
        name for name in allowed
        if any(name in {f"shared_{project}", f"private_{sanitize_identifier(owner)}_{project}"} for project in requested)
    ]
    missing = [
        project for project in requested
        if not any(name in {f"shared_{project}", f"private_{sanitize_identifier(owner)}_{project}"} for name in allowed)
    ]
    if missing:
        raise ValueError(f"参照可能なプロジェクトが見つかりません: {', '.join(missing)}")
    return sorted(set(selected))


def _payload_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    nested = metadata.get("metadata")
    return {**metadata, **nested} if isinstance(nested, dict) else metadata


def _payload_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("text"), str):
        return payload["text"]
    metadata = payload.get("metadata")
    if isinstance(metadata, dict) and isinstance(metadata.get("text"), str):
        return metadata["text"]
    raw_node = payload.get("_node_content")
    if isinstance(raw_node, str):
        try:
            node = json.loads(raw_node)
            text = node.get("text") or node.get("text_resource", {}).get("text")
            return text if isinstance(text, str) else ""
        except json.JSONDecodeError:
            return ""
    return ""


def search_knowledge(
    query: str,
    owner: str,
    projects: Iterable[str] | None = None,
    limit: int = DEFAULT_SEARCH_LIMIT,
    *,
    client: QdrantClient | None = None,
) -> list[SearchResult]:
    query = query.strip()
    if not query:
        raise ValueError("検索文が空です")

    limit = max(1, min(int(limit), MAX_SEARCH_LIMIT))
    qdrant = client or make_qdrant_client()
    collections = resolve_collections(qdrant, owner, projects)
    if not collections:
        return []

    vector = embed_query(query)
    results: list[SearchResult] = []
    for collection in collections:
        response = qdrant.query_points(
            collection_name=collection,
            query=vector,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        for point in response.points:
            payload = point.payload or {}
            metadata = _payload_metadata(payload)
            results.append(SearchResult(
                score=float(point.score),
                collection=collection,
                project_id=str(metadata.get("project_id", "")),
                project_name=str(metadata.get("project_name", metadata.get("project_id", ""))),
                scope=str(metadata.get("scope", "")),
                owner=str(metadata.get("owner", "")),
                relative_path=str(metadata.get("relative_path", "")),
                logical_path=str(metadata.get("logical_path", "")),
                source_ref=str(metadata.get("source_ref", metadata.get("logical_path", ""))),
                chunk_index=int(metadata.get("chunk_index", 0) or 0),
                text=_payload_text(payload),
            ))

    results.sort(key=lambda item: item.score, reverse=True)
    return results[:limit]


def list_knowledge_projects(owner: str, *, client: QdrantClient | None = None) -> list[dict[str, Any]]:
    qdrant = client or make_qdrant_client()
    projects = []
    for collection in accessible_collections(qdrant, owner):
        points, _ = qdrant.scroll(collection_name=collection, limit=1, with_payload=True, with_vectors=False)
        metadata = _payload_metadata(points[0].payload or {}) if points else {}
        projects.append({
            "collection": collection,
            "project_id": str(metadata.get("project_id", "")),
            "project_name": str(metadata.get("project_name", metadata.get("project_id", ""))),
            "scope": str(metadata.get("scope", "shared" if collection.startswith("shared_") else "personal")),
            "owner": str(metadata.get("owner", "shared")),
        })
    return projects


def _resolve_source_path(source_ref: str, owner: str) -> Path:
    parsed = urlparse(source_ref)
    expected_scheme = urlparse(KNOWLEDGE_LOGICAL_ROOT).scheme or "labknowledge"
    if parsed.scheme not in {expected_scheme, "kbsource"}:
        raise ValueError("このシステムが発行したsource_refではありません")

    parts = [unquote(parsed.netloc), *[unquote(p) for p in parsed.path.split("/") if p]] if parsed.netloc else [
        unquote(p) for p in parsed.path.split("/") if p
    ]
    if len(parts) < 3:
        raise ValueError("logical_pathの形式が不正です")

    if parts[0] == "shared":
        base = KNOWLEDGE_ROOT / "shared" / parts[1]
        relative_parts = parts[2:]
    elif parts[0] == "users":
        if len(parts) < 4:
            raise ValueError("個人logical_pathの形式が不正です")
        ref_owner = sanitize_identifier(parts[1])
        if ref_owner != sanitize_identifier(owner):
            raise PermissionError("他ユーザーの個人ナレッジは参照できません")
        base = KNOWLEDGE_ROOT / "users" / ref_owner / parts[2]
        relative_parts = parts[3:]
    else:
        raise ValueError("未知のKnowledge scopeです")

    base = base.resolve()
    target = base.joinpath(*relative_parts).resolve()
    if not target.is_relative_to(base):
        raise PermissionError("Knowledgeルート外のパスは参照できません")
    return target


def read_knowledge_source(source_ref: str, owner: str, start_line: int = 1, max_lines: int = 200) -> dict[str, Any]:
    target = _resolve_source_path(source_ref, owner)
    if not target.is_file():
        raise FileNotFoundError(f"原本が見つかりません: {source_ref}")
    if target.suffix.lower() not in READABLE_EXTENSIONS:
        raise ValueError(f"原本参照に対応していない形式です: {target.suffix.lower()}")

    start_line = max(1, int(start_line))
    max_lines = max(1, min(int(max_lines), MAX_SOURCE_LINES))
    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    selected = lines[start_line - 1:start_line - 1 + max_lines]
    end_line = start_line + len(selected) - 1
    return {
        "source_ref": source_ref,
        "start_line": start_line,
        "end_line": end_line,
        "total_lines": len(lines),
        "truncated": end_line < len(lines),
        "text": "\n".join(f"{number:>6}: {line}" for number, line in enumerate(selected, start=start_line)),
    }
