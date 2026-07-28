from __future__ import annotations

import os
import re
from pathlib import Path

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY") or None
LITELLM_API_BASE = os.environ.get("LITELLM_API_BASE", "http://localhost:4000/v1").rstrip("/")
LITELLM_API_KEY = os.environ.get("LITELLM_API_KEY", "")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "lab-embedding")
_logical_root = os.environ.get("KNOWLEDGE_LOGICAL_ROOT", "labknowledge://")
KNOWLEDGE_LOGICAL_ROOT = _logical_root if _logical_root.endswith("://") else _logical_root.rstrip("/") + "/"
KNOWLEDGE_ROOT = Path(os.environ.get("KNOWLEDGE_ROOT", "/knowledge")).expanduser()
INCOMING_ROOT = Path(os.environ.get("INCOMING_ROOT", "/incoming")).expanduser()


def sanitize_identifier(value: str, max_length: int = 120) -> str:
    value = re.sub(r"[^a-z0-9._-]+", "-", value.strip().lower())
    value = re.sub(r"-{2,}", "-", value).strip("-._")
    if not value:
        raise ValueError("識別子が空になりました")
    return value[:max_length]


def collection_name_for(project_id: str, shared: bool, owner: str) -> str:
    return f"shared_{project_id}" if shared else f"private_{owner}_{project_id}"


def logical_path_for(relative_path: str, project_id: str, shared: bool, owner: str) -> str:
    prefix = f"shared/{project_id}" if shared else f"users/{owner}/{project_id}"
    return f"{KNOWLEDGE_LOGICAL_ROOT}{prefix}/{relative_path}"
