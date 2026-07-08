from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class QdrantConfig(BaseModel):
    host: str = "qdrant"
    port: int = 6333
    collection: str = "lab_knowledge"


class EmbeddingConfig(BaseModel):
    model: str = "BAAI/bge-m3"


class ChunkingConfig(BaseModel):
    chunk_size: int = 1024
    chunk_overlap: int = 128


class SearchConfig(BaseModel):
    similarity_top_k: int = 5


class KnowledgeConfig(BaseModel):
    mode: str = "simple"  # simple or home
    root: str = "/knowledge"
    owner: str = "default"
    home_root: str = "/host_home"
    knowledge_dir_name: str = "knowledge"
    shared_owner: str = "share"


class AdminConfig(BaseModel):
    username_header: str = "x-authentik-username"
    allow_header_auth: bool = True


class MetadataRule(BaseModel):
    pattern: str
    metadata: dict[str, str] = Field(default_factory=dict)


class AppConfig(BaseModel):
    knowledge: KnowledgeConfig = Field(default_factory=KnowledgeConfig)
    qdrant: QdrantConfig = Field(default_factory=QdrantConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    admin: AdminConfig = Field(default_factory=AdminConfig)
    metadata_rules: list[MetadataRule] = Field(default_factory=list)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config() -> AppConfig:
    config_path = Path(os.getenv("FKB_CONFIG", "/app/config.yaml"))
    data = _load_yaml(config_path)
    cfg = AppConfig.model_validate(data)

    cfg.qdrant.host = os.getenv("QDRANT_HOST", cfg.qdrant.host)
    cfg.qdrant.port = int(os.getenv("QDRANT_PORT", str(cfg.qdrant.port)))
    cfg.qdrant.collection = os.getenv("QDRANT_COLLECTION", cfg.qdrant.collection)

    cfg.knowledge.root = os.getenv("KNOWLEDGE_DIR", cfg.knowledge.root)
    cfg.knowledge.owner = os.getenv("KNOWLEDGE_OWNER", cfg.knowledge.owner)

    cfg.embedding.model = os.getenv("EMBED_MODEL", cfg.embedding.model)
    cfg.chunking.chunk_size = int(os.getenv("CHUNK_SIZE", str(cfg.chunking.chunk_size)))
    cfg.chunking.chunk_overlap = int(os.getenv("CHUNK_OVERLAP", str(cfg.chunking.chunk_overlap)))
    cfg.search.similarity_top_k = int(os.getenv("SIMILARITY_TOP_K", str(cfg.search.similarity_top_k)))

    cfg.admin.username_header = os.getenv("FKB_AUTH_USERNAME_HEADER", cfg.admin.username_header).lower()
    cfg.admin.allow_header_auth = os.getenv("FKB_ADMIN_ALLOW_HEADER_AUTH", str(cfg.admin.allow_header_auth)).lower() in ("1", "true", "yes")

    return cfg


def knowledge_root_for_owner(cfg: AppConfig, owner: str | None = None) -> Path:
    if cfg.knowledge.mode == "home":
        if not owner:
            owner = cfg.knowledge.owner
        return Path(cfg.knowledge.home_root) / owner / cfg.knowledge.knowledge_dir_name
    return Path(cfg.knowledge.root)


def owner_for_simple_mode(cfg: AppConfig) -> str:
    return cfg.knowledge.owner
