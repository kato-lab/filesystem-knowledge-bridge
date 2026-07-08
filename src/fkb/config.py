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
    root: str = "/knowledge"


class MetadataRule(BaseModel):
    pattern: str
    metadata: dict[str, str] = Field(default_factory=dict)


class AppConfig(BaseModel):
    knowledge: KnowledgeConfig = Field(default_factory=KnowledgeConfig)
    qdrant: QdrantConfig = Field(default_factory=QdrantConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
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

    cfg.knowledge.root = os.getenv("KNOWLEDGE_DIR", cfg.knowledge.root)
    cfg.qdrant.host = os.getenv("QDRANT_HOST", cfg.qdrant.host)
    cfg.qdrant.port = int(os.getenv("QDRANT_PORT", str(cfg.qdrant.port)))
    cfg.qdrant.collection = os.getenv("QDRANT_COLLECTION", cfg.qdrant.collection)
    cfg.embedding.model = os.getenv("EMBED_MODEL", cfg.embedding.model)
    cfg.chunking.chunk_size = int(os.getenv("CHUNK_SIZE", str(cfg.chunking.chunk_size)))
    cfg.chunking.chunk_overlap = int(os.getenv("CHUNK_OVERLAP", str(cfg.chunking.chunk_overlap)))
    cfg.search.similarity_top_k = int(os.getenv("SIMILARITY_TOP_K", str(cfg.search.similarity_top_k)))
    return cfg
