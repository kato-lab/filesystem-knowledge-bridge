#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path
from typing import Iterable
from uuid import NAMESPACE_URL, uuid5

from kb_common import (
    EMBEDDING_MODEL,
    LITELLM_API_BASE,
    LITELLM_API_KEY,
    QDRANT_API_KEY,
    QDRANT_URL,
    collection_name_for,
    logical_path_for,
    sanitize_identifier,
)

TEXT_EXTENSIONS = {".txt", ".rst", ".yaml", ".yml", ".json", ".csv", ".toml", ".ini", ".cfg", ".tex"}
MARKDOWN_EXTENSIONS = {".md", ".markdown"}
CODE_LANGUAGES = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "tsx", ".java": "java",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp",
    ".cxx": "cpp", ".hpp": "cpp", ".cs": "c_sharp",
    ".go": "go", ".rs": "rust", ".rb": "ruby", ".php": "php",
}
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".pptx"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | MARKDOWN_EXTENSIONS | set(CODE_LANGUAGES) | DOCUMENT_EXTENSIONS


def common_metadata(
    path: Path,
    target_dir: Path,
    project_id: str,
    project_name: str,
    shared: bool,
    owner: str,
) -> dict[str, object]:
    relative_path = path.relative_to(target_dir).as_posix()
    parts = relative_path.split("/")
    return {
        "scope": "shared" if shared else "personal",
        "owner": "shared" if shared else owner,
        "project_id": project_id,
        "project_name": project_name,
        "relative_path": relative_path,
        "logical_path": logical_path_for(relative_path, project_id, shared, owner),
        "source_ref": (
            f"kbsource://shared/{target_dir.name}/{relative_path}"
            if shared
            else f"kbsource://users/{owner}/{target_dir.name}/{relative_path}"
        ),
        "file_name": path.name,
        "file_extension": path.suffix.lower(),
        "top_directory": parts[0] if len(parts) > 1 else "",
    }


def iter_supported_files(target_dir: Path) -> Iterable[Path]:
    for path in sorted(target_dir.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        if any(part.startswith(".") for part in path.relative_to(target_dir).parts):
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            print(f"⚠️  未対応のためスキップ: {path.relative_to(target_dir)}")
            continue
        yield path


def _read_text_document(path: Path):
    from llama_index.core import Document

    return [Document(text=path.read_text(encoding="utf-8", errors="replace"))]


def parse_file(path: Path):
    from llama_index.core.node_parser import CodeSplitter, MarkdownNodeParser, SentenceSplitter

    suffix = path.suffix.lower()
    if suffix in MARKDOWN_EXTENSIONS:
        return MarkdownNodeParser().get_nodes_from_documents(_read_text_document(path))
    if suffix in CODE_LANGUAGES:
        documents = _read_text_document(path)
        try:
            return CodeSplitter(
                language=CODE_LANGUAGES[suffix],
                chunk_lines=80,
                chunk_lines_overlap=10,
                max_chars=8000,
            ).get_nodes_from_documents(documents)
        except Exception as exc:
            print(f"⚠️  CodeSplitter失敗、通常分割へfallback: {path.name} ({exc})")
            return SentenceSplitter(chunk_size=1024, chunk_overlap=128).get_nodes_from_documents(documents)
    if suffix in DOCUMENT_EXTENSIONS:
        from llama_index.readers.file import DocxReader, PDFReader, PptxReader

        if suffix == ".pdf":
            documents = PDFReader().load_data(file=path)
        elif suffix == ".docx":
            documents = DocxReader().load_data(file=path)
        else:
            documents = PptxReader().load_data(file=path)
        return SentenceSplitter(chunk_size=1024, chunk_overlap=128).get_nodes_from_documents(documents)
    return SentenceSplitter(chunk_size=1024, chunk_overlap=128).get_nodes_from_documents(_read_text_document(path))


def configure_embedding() -> None:
    if not LITELLM_API_KEY:
        raise RuntimeError("LITELLM_API_KEYが未設定です")

    from llama_index.core import Settings
    from llama_index.embeddings.openai_like import OpenAILikeEmbedding

    Settings.embed_model = OpenAILikeEmbedding(
        model_name=EMBEDDING_MODEL,
        api_base=LITELLM_API_BASE,
        api_key=LITELLM_API_KEY,
        embed_batch_size=10,
        additional_kwargs={"encoding_format": "float"},
    )


def build_nodes(target_dir: Path, project_id: str, project_name: str, shared: bool, owner: str):
    final_nodes = []
    for path in iter_supported_files(target_dir):
        relative_path = path.relative_to(target_dir).as_posix()
        print(f"📄 処理中: {relative_path}")
        try:
            nodes = parse_file(path)
        except Exception as exc:
            print(f"❌ パース失敗: {relative_path}: {exc}")
            continue

        metadata = common_metadata(path, target_dir, project_id, project_name, shared, owner)
        for index, node in enumerate(nodes):
            logical_id = f"{'shared' if shared else owner}:{project_id}:{relative_path}:{index}"
            node.metadata.update(metadata)
            node.metadata["chunk_index"] = index
            node.metadata["logical_id"] = logical_id
            node.metadata["text"] = node.get_content()
            node.metadata["metadata"] = {**metadata, "chunk_index": index, "logical_id": logical_id}
            node.excluded_embed_metadata_keys.extend(["text", "metadata"])
            node.excluded_llm_metadata_keys.extend(["text", "metadata"])
            node.id_ = str(uuid5(NAMESPACE_URL, logical_id))

        final_nodes.extend(nodes)
        print(f"   └─ {len(nodes)} node")
    return final_nodes


def replace_collection_and_index(collection_name: str, nodes) -> None:
    from llama_index.core import StorageContext, VectorStoreIndex
    from llama_index.vector_stores.qdrant import QdrantVectorStore
    from qdrant_client import QdrantClient

    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    if client.collection_exists(collection_name):
        print(f"🗑️  既存collectionを削除: {collection_name}")
        client.delete_collection(collection_name=collection_name)
    vector_store = QdrantVectorStore(client=client, collection_name=collection_name)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    VectorStoreIndex(nodes=nodes, storage_context=storage_context, show_progress=True)


def index_directory(
    target_dir: Path,
    *,
    shared: bool = False,
    owner: str | None = None,
    project_id: str | None = None,
    collection: str | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    target_dir = target_dir.expanduser().resolve()
    if not target_dir.is_dir():
        raise FileNotFoundError(f"フォルダが見つかりません: {target_dir}")

    project_name = target_dir.name
    resolved_project_id = sanitize_identifier(project_id or project_name)
    resolved_owner = sanitize_identifier(owner or getpass.getuser() or "unknown")
    collection_name = (
        sanitize_identifier(collection)
        if collection
        else collection_name_for(resolved_project_id, shared, resolved_owner)
    )

    print(f"🚀 {'共有' if shared else '個人'} Knowledgeを登録します")
    print(f"   project: {project_name} ({resolved_project_id})")
    print(f"   source: {target_dir}")
    print(f"   collection: {collection_name}")

    configure_embedding()
    nodes = build_nodes(target_dir, resolved_project_id, project_name, shared, resolved_owner)
    if not nodes:
        raise RuntimeError("nodeが生成されませんでした")

    print(f"✅ 合計node数: {len(nodes)}")
    if dry_run:
        for node in nodes[:5]:
            print(node.metadata)
    else:
        print("🛰️  Embedding生成・Qdrant登録中...")
        replace_collection_and_index(collection_name, nodes)
        print(f"✨ 登録完了: {collection_name}")

    return {
        "project": project_name,
        "project_id": resolved_project_id,
        "owner": "shared" if shared else resolved_owner,
        "scope": "shared" if shared else "personal",
        "collection": collection_name,
        "nodes": len(nodes),
        "dry_run": dry_run,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="構造保持型RAG Knowledge登録ツール")
    parser.add_argument("dir", type=Path, help="Knowledge化するプロジェクトフォルダ")
    parser.add_argument("--shared", action="store_true", help="共有Knowledgeとして登録")
    parser.add_argument("--owner", help="個人Knowledgeのowner。省略時はOSユーザ")
    parser.add_argument("--project-id", help="安定したproject識別子。省略時はフォルダ名")
    parser.add_argument("--collection", help="Qdrant collection名。省略時はscope/owner/project-idから自動生成")
    parser.add_argument("--dry-run", action="store_true", help="Qdrantへ登録せずmetadataを確認")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        index_directory(
            args.dir,
            shared=args.shared,
            owner=args.owner,
            project_id=args.project_id,
            collection=args.collection,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        print(f"❌ {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
