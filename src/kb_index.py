#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
from pathlib import Path
from typing import Iterable

from qdrant_client import QdrantClient
from llama_index.core import Document, Settings, StorageContext, VectorStoreIndex
from llama_index.core.node_parser import CodeSplitter, MarkdownNodeParser, SentenceSplitter
from llama_index.embeddings.openai_like import OpenAILikeEmbedding
from llama_index.readers.file import DocxReader, PDFReader, PptxReader
from llama_index.vector_stores.qdrant import QdrantVectorStore
from uuid import NAMESPACE_URL, uuid5

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY") or None
LITELLM_API_BASE = os.environ.get("LITELLM_API_BASE", "http://localhost:4000/v1")
LITELLM_API_KEY = os.environ.get("LITELLM_API_KEY", "")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "lab-embedding")
KNOWLEDGE_LOGICAL_ROOT = os.environ.get("KNOWLEDGE_LOGICAL_ROOT", "labknowledge://").rstrip("/") + "/"

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

# -----------------------------------------------------------------------
# Sanitization of identifiers for collection names, project IDs, and owner names.
# -----------------------------------------------------------------------
def sanitize_identifier(value: str, max_length: int = 120) -> str:
    value = re.sub(r"[^a-z0-9._-]+", "-", value.strip().lower())
    value = re.sub(r"-{2,}", "-", value).strip("-._")
    if not value:
        raise ValueError("識別子が空になりました")
    return value[:max_length]

# -----------------------------------------------------------------------
# Collection name and logical path generation for Qdrant.
# -----------------------------------------------------------------------
def collection_name_for(project_id: str, shared: bool, owner: str) -> str:
    return f"shared_{project_id}" if shared else f"private_{owner}_{project_id}"

# -----------------------------------------------------------------------
# Logical path generation for knowledge nodes.
# -----------------------------------------------------------------------
def logical_path_for(relative_path: str, project_id: str, shared: bool, owner: str) -> str:
    prefix = f"shared/{project_id}" if shared else f"users/{owner}/{project_id}"
    return f"{KNOWLEDGE_LOGICAL_ROOT}{prefix}/{relative_path}"

# -----------------------------------------------------------------------
# Metadata generation for knowledge nodes.
# -----------------------------------------------------------------------
def common_metadata(path: Path, target_dir: Path, project_id: str, project_name: str, shared: bool, owner: str) -> dict[str, object]:
    relative_path = path.relative_to(target_dir).as_posix()
    parts = relative_path.split("/")
    return {
        "scope": "shared" if shared else "personal",
        "owner": "shared" if shared else owner,
        "project_id": project_id,
        "project_name": project_name,
        "relative_path": relative_path,
        "logical_path": logical_path_for(relative_path, project_id, shared, owner),
        "file_name": path.name,
        "file_extension": path.suffix.lower(),
        "top_directory": parts[0] if len(parts) > 1 else "",
    }

# -----------------------------------------------------------------------
# File iteration and parsing functions.
# -----------------------------------------------------------------------
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

# -----------------------------------------------------------------------
# Parsing functions for text documents.
# -----------------------------------------------------------------------
def read_text_document(path: Path) -> list[Document]:
    return [Document(text=path.read_text(encoding="utf-8", errors="replace"))]

# -----------------------------------------------------------------------
# Parsing functions for Markdown, code, plain text, and structured documents.
# -----------------------------------------------------------------------
def parse_markdown(path: Path):
    return MarkdownNodeParser().get_nodes_from_documents(read_text_document(path))

# -----------------------------------------------------------------------
# Parsing functions for code files with fallback to sentence splitting.
# -----------------------------------------------------------------------
def parse_code(path: Path, language: str):
    documents = read_text_document(path)
    try:
        return CodeSplitter(language=language, chunk_lines=80, chunk_lines_overlap=10, max_chars=8000).get_nodes_from_documents(documents)
    except Exception as exc:
        print(f"⚠️  CodeSplitter失敗、通常分割へfallback: {path.name} ({exc})")
        return SentenceSplitter(chunk_size=1024, chunk_overlap=128).get_nodes_from_documents(documents)

# -----------------------------------------------------------------------
# Parsing functions for plain text and structured documents.
# -----------------------------------------------------------------------
def parse_plain_text(path: Path):
    return SentenceSplitter(chunk_size=1024, chunk_overlap=128).get_nodes_from_documents(read_text_document(path))

# -----------------------------------------------------------------------
# Parsing functions for structured documents (PDF, DOCX, PPTX).
# -----------------------------------------------------------------------
def load_structured_documents(path: Path) -> list[Document]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return PDFReader().load_data(file=path)
    if suffix == ".docx":
        return DocxReader().load_data(file=path)
    if suffix == ".pptx":
        return PptxReader().load_data(file=path)
    raise ValueError(f"未対応形式: {suffix}")

# -----------------------------------------------------------------------
# Parsing functions for structured documents with sentence splitting.
# -----------------------------------------------------------------------
def parse_structured_document(path: Path):
    documents = load_structured_documents(path)
    return SentenceSplitter(chunk_size=1024, chunk_overlap=128).get_nodes_from_documents(documents)

# -----------------------------------------------------------------------
# Main parsing function that dispatches based on file extension.
# -----------------------------------------------------------------------
def parse_file(path: Path):
    suffix = path.suffix.lower()
    if suffix in MARKDOWN_EXTENSIONS:
        return parse_markdown(path)
    if suffix in CODE_LANGUAGES:
        return parse_code(path, CODE_LANGUAGES[suffix])
    if suffix in DOCUMENT_EXTENSIONS:
        return parse_structured_document(path)
    return parse_plain_text(path)

# -----------------------------------------------------------------------
# Embedding configuration function that checks for API key and sets the embedding model.
# -----------------------------------------------------------------------
def configure_embedding() -> None:
    if not LITELLM_API_KEY:
        raise RuntimeError("LITELLM_API_KEYが未設定です")

    Settings.embed_model = OpenAILikeEmbedding(
        model_name=EMBEDDING_MODEL,
        api_base=LITELLM_API_BASE,
        api_key=LITELLM_API_KEY,
        embed_batch_size=10,
        additional_kwargs={
            "encoding_format": "float",
        },
    )
# -----------------------------------------------------------------------
# Node building function that processes files and generates nodes with metadata.
# -----------------------------------------------------------------------
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
            node.metadata.update(metadata)
            node.metadata["chunk_index"] = index

            logical_id = (
                f"{'shared' if shared else owner}:"
                f"{project_id}:"
                f"{relative_path}:"
                f"{index}"
            )

            node.metadata["logical_id"] = logical_id
            node.id_ = str(uuid5(NAMESPACE_URL, logical_id))
        final_nodes.extend(nodes)
        print(f"   └─ {len(nodes)} node")
    return final_nodes

# -----------------------------------------------------------------------
# Function to replace the collection and index in Qdrant with new nodes.
# -----------------------------------------------------------------------
def replace_collection_and_index(client: QdrantClient, collection_name: str, nodes) -> None:
    if client.collection_exists(collection_name):
        print(f"🗑️  既存collectionを削除: {collection_name}")
        client.delete_collection(collection_name=collection_name)
    vector_store = QdrantVectorStore(client=client, collection_name=collection_name)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    VectorStoreIndex(nodes=nodes, storage_context=storage_context, show_progress=True)

# -----------------------------------------------------------------------
# Argument parsing function for command-line interface.
# -----------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="構造保持型RAG Knowledge登録ツール")
    parser.add_argument("dir", type=Path, help="Knowledge化するプロジェクトフォルダ")
    parser.add_argument("--shared", action="store_true", help="共有Knowledgeとして登録")
    parser.add_argument("--owner", help="個人Knowledgeのowner。省略時はOSユーザ")
    parser.add_argument("--project-id", help="安定したproject識別子。省略時はフォルダ名")
    parser.add_argument("--collection", help="Qdrant collection名。省略時はscope/owner/project-idから自動生成")
    parser.add_argument("--dry-run", action="store_true", help="Qdrantへ登録せずmetadataを確認")
    return parser.parse_args()

# -----------------------------------------------------------------------
# Main function that orchestrates the entire process of building and registering knowledge nodes.
# -----------------------------------------------------------------------
def main() -> None:
    args = parse_args()
    target_dir = args.dir.expanduser().resolve()
    if not target_dir.is_dir():
        print(f"❌ フォルダが見つかりません: {target_dir}", file=sys.stderr)
        raise SystemExit(1)

    project_name = target_dir.name
    project_id = sanitize_identifier(args.project_id or project_name)
    # --sharedでない場合、--owner省略時はスクリプト実行中のOSアカウント名を使用する。
    # getpass.getuser()はLOGNAME/USER/LNAME/USERNAME等を参照するため、sudo実行時は
    # rootになる場合がある。必要なら --owner で明示する。
    owner = sanitize_identifier(args.owner or getpass.getuser() or "unknown")
    collection_name = (
        sanitize_identifier(args.collection)
        if args.collection
        else collection_name_for(project_id, args.shared, owner)
    )

    print(f"🚀 {'共有' if args.shared else '個人'} Knowledgeを登録します")
    print(f"   project: {project_name} ({project_id})")
    print(f"   source: {target_dir}")
    print(f"   collection: {collection_name}")

    configure_embedding()
    nodes = build_nodes(target_dir, project_id, project_name, args.shared, owner)
    if not nodes:
        print("❌ nodeが生成されませんでした", file=sys.stderr)
        raise SystemExit(2)

    print(f"✅ 合計node数: {len(nodes)}")
    if args.dry_run:
        print("🔎 dry-run")
        for node in nodes[:5]:
            print(node.metadata)
        return

    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    print("🛰️  Embedding生成・Qdrant登録中...")
    replace_collection_and_index(client, collection_name, nodes)
    print(f"✨ 登録完了: {collection_name}")


if __name__ == "__main__":
    main()
