from __future__ import annotations

import os
import re
from pathlib import Path

from mcp.server.transport_security import TransportSecuritySettings

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY") or None
LITELLM_API_BASE = os.environ.get("LITELLM_API_BASE", "http://localhost:4000/v1").rstrip("/")
LITELLM_API_KEY = os.environ.get("LITELLM_API_KEY", "")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "lab-embedding")
KNOWLEDGE_ROOT = Path(os.environ.get("KNOWLEDGE_ROOT", "/knowledge"))
INCOMING_ROOT = Path(os.environ.get("INCOMING_ROOT", "/incoming"))
KNOWLEDGE_LOGICAL_ROOT = os.environ.get("KNOWLEDGE_LOGICAL_ROOT", "labknowledge://")


def _csv_env(name: str, default: str = "") -> list[str]:
    """カンマ区切りの環境変数を空要素なしのリストへ変換します。"""
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


def create_transport_security(default_port: int) -> TransportSecuritySettings:
    """MCP HTTP transportのHost検証設定を環境変数から生成します。

    Dockerサービス名やリバースプロキシ名は実行環境ごとに異なるため、
    ソースコードには固定せず ``MCP_ALLOWED_HOSTS`` で指定します。
    未指定時はローカル接続だけを許可します。
    """
    default_hosts = f"localhost:{default_port},127.0.0.1:{default_port}"
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=_csv_env("MCP_ALLOWED_HOSTS", default_hosts),
    )


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
    root = KNOWLEDGE_LOGICAL_ROOT.rstrip("/")
    return f"{root}//{prefix}/{relative_path.lstrip('/')}"


def resolve_under(root: Path, *parts: str) -> Path:
    root = root.resolve()
    target = root.joinpath(*parts).resolve()
    if not target.is_relative_to(root):
        raise ValueError("許可されたディレクトリの外は参照できません")
    return target
