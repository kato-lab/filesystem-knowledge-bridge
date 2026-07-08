# filesystem-knowledge-bridge

A small example project for building a filesystem-based AI knowledge layer.

This repository accompanies an article series about building a laboratory AI infrastructure with OpenWebUI + LiteLLM.

The goal is not to replace existing RAG platforms. The goal is to keep your existing folder structure as the source of truth and expose it to AI tools through MCP.

## Concept

```text
Existing filesystem
  knowledge/
    projects/
    thesis/
    manuals/
        ↓
Path-aware indexer
        ↓
Qdrant
        ↓
MCP server
        ↓
OpenWebUI / VSCode Agent / Cursor / other MCP clients
```

## What this project does

- Recursively reads a local folder
- Keeps relative file paths as metadata
- Indexes documents into Qdrant
- Provides a simple search command
- Provides an MCP server for AI tools

## What this project does not do

- It is not a chat UI
- It is not an LLM gateway
- It is not a full document management system
- It does not replace OpenWebUI, LiteLLM, Qdrant, or LlamaIndex

## Quick start

```bash
cp .env.example .env
cp config.example.yaml config.yaml

docker compose up -d qdrant

docker compose run --rm indexer

docker compose run --rm search "sample project experiment condition"

docker compose up -d mcp
```

Qdrant dashboard:

```text
http://localhost:6333/dashboard
```

## Directory structure

```text
filesystem-knowledge-bridge/
├── docker-compose.yml
├── config.example.yaml
├── .env.example
├── knowledge/
│   ├── projects/
│   └── manuals/
├── src/
│   └── fkb/
│       ├── config.py
│       ├── metadata.py
│       ├── rag_core.py
│       ├── indexer.py
│       ├── search.py
│       └── mcp_server.py
└── docs/
```

## Path-aware metadata

For a file such as:

```text
knowledge/projects/sample_project/experiments/2026-07-08.md
```

this project stores metadata like:

```json
{
  "source_path": "projects/sample_project/experiments/2026-07-08.md",
  "top_dir": "projects",
  "project": "sample_project",
  "filename": "2026-07-08.md"
}
```

The exact metadata extraction rules can be customized in `config.yaml`.

## Notes

This is an intentionally small bridge layer. The first target is to make the folder structure visible to AI tools without forcing users to move all documents into an application-specific knowledge base.
