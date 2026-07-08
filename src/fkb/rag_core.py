from __future__ import annotations

import qdrant_client
from llama_index.core import Settings, StorageContext, VectorStoreIndex
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore

from .config import AppConfig, load_config


def configure_llamaindex(cfg: AppConfig):
    Settings.embed_model = HuggingFaceEmbedding(model_name=cfg.embedding.model)
    Settings.node_parser = SentenceSplitter(
        chunk_size=cfg.chunking.chunk_size,
        chunk_overlap=cfg.chunking.chunk_overlap,
    )


def get_qdrant_client(cfg: AppConfig | None = None) -> qdrant_client.QdrantClient:
    cfg = cfg or load_config()
    return qdrant_client.QdrantClient(host=cfg.qdrant.host, port=cfg.qdrant.port)


def get_vector_store(cfg: AppConfig | None = None) -> QdrantVectorStore:
    cfg = cfg or load_config()
    return QdrantVectorStore(client=get_qdrant_client(cfg), collection_name=cfg.qdrant.collection)


def get_index(cfg: AppConfig | None = None) -> VectorStoreIndex:
    cfg = cfg or load_config()
    configure_llamaindex(cfg)
    vector_store = get_vector_store(cfg)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    return VectorStoreIndex.from_vector_store(vector_store=vector_store, storage_context=storage_context)
