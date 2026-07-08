from __future__ import annotations

import argparse
from pathlib import Path

from llama_index.core import Document, SimpleDirectoryReader, StorageContext, VectorStoreIndex

from .config import knowledge_root_for_owner, load_config, owner_for_simple_mode
from .metadata import build_metadata
from .rag_core import configure_llamaindex, get_vector_store


DEFAULT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst",
    ".py", ".yaml", ".yml", ".json", ".csv", ".tex",
}


def load_documents(root: Path, owner: str):
    cfg = load_config()
    documents: list[Document] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        if path.suffix.lower() not in DEFAULT_EXTENSIONS:
            continue
        rel_path = path.relative_to(root).as_posix()
        metadata = build_metadata(path, root, owner, cfg.metadata_rules)
        try:
            loaded = SimpleDirectoryReader(input_files=[str(path)], filename_as_id=True).load_data()
        except Exception as exc:
            print(f"[WARN] failed to load {rel_path}: {exc}")
            continue
        for doc in loaded:
            doc.metadata.update(metadata)
            doc.id_ = f"{owner}:{rel_path}"
            documents.append(doc)
    return documents


def index_owner(owner: str | None = None):
    cfg = load_config()
    configure_llamaindex(cfg)
    if cfg.knowledge.mode == "simple":
        owner = owner or owner_for_simple_mode(cfg)
    elif not owner:
        raise ValueError("owner is required in home mode")
    root = knowledge_root_for_owner(cfg, owner)
    if not root.exists():
        raise FileNotFoundError(f"Knowledge root not found: {root}")
    print(f"[INFO] owner: {owner}")
    print(f"[INFO] knowledge root: {root}")
    documents = load_documents(root, owner)
    print(f"[INFO] loaded documents: {len(documents)}")
    vector_store = get_vector_store(cfg)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    VectorStoreIndex.from_documents(documents, storage_context=storage_context, show_progress=True)
    print(f"[INFO] indexed into collection: {cfg.qdrant.collection}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner", default=None, help="Owner username for home mode")
    args = parser.parse_args()
    index_owner(args.owner)


if __name__ == "__main__":
    main()
