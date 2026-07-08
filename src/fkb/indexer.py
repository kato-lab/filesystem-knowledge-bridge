from __future__ import annotations

from pathlib import Path

from llama_index.core import Document, SimpleDirectoryReader, StorageContext, VectorStoreIndex

from .config import load_config
from .metadata import build_metadata
from .rag_core import configure_llamaindex, get_vector_store, knowledge_root


DEFAULT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst", ".py", ".yaml", ".yml", ".json", ".csv", ".tex"
}


def load_documents(root: Path):
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
        metadata = build_metadata(path, root, cfg.metadata_rules)
        try:
            loaded = SimpleDirectoryReader(input_files=[str(path)], filename_as_id=True).load_data()
        except Exception as exc:
            print(f"[WARN] failed to load {rel_path}: {exc}")
            continue

        for doc in loaded:
            doc.metadata.update(metadata)
            doc.id_ = rel_path
            documents.append(doc)
    return documents


def main():
    cfg = load_config()
    configure_llamaindex(cfg)
    root = knowledge_root(cfg)
    if not root.exists():
        raise FileNotFoundError(f"Knowledge root not found: {root}")

    print(f"[INFO] knowledge root: {root}")
    documents = load_documents(root)
    print(f"[INFO] loaded documents: {len(documents)}")

    vector_store = get_vector_store(cfg)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    VectorStoreIndex.from_documents(documents, storage_context=storage_context, show_progress=True)
    print(f"[INFO] indexed documents into collection: {cfg.qdrant.collection}")


if __name__ == "__main__":
    main()
