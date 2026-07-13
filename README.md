# filesystem-knowledge-bridge

A lightweight indexing tool for registering frozen project folders as Qdrant collections and using them from Open WebUI through External Knowledge Sources.

> Keep the architecture simple: reuse existing RAG components and customize only the indexing step.

Japanese documentation: [README.ja.md](README.ja.md)

## Overview

```text
Frozen project folder
        │
        ▼
     kb-index
        │
        ├── LiteLLM ── TEI / BGE-M3
        │
        ▼
      Qdrant
        │
        ▼
Open WebUI External Knowledge Sources
```

The project does not provide a custom search server. Open WebUI searches the Qdrant collection directly.

## Features

- Preserves project and relative path metadata
- Creates one Qdrant collection per project by default
- Supports shared and personal knowledge
- Supports Markdown, source code, plain text, PDF, DOCX, and PPTX
- Uses file-type-specific chunking
- Generates embeddings through an OpenAI-compatible LiteLLM endpoint
- Stores Open WebUI-compatible `text` and `metadata` payload fields
- Replaces an existing collection when re-indexing
- Provides a host-side CLI and an optional containerized execution path

## Requirements

- Linux or macOS
- Python 3.11 or later
- [uv](https://docs.astral.sh/uv/)
- Docker and Docker Compose
- Open WebUI 0.10.2 or later
- LiteLLM Proxy
- Qdrant
- An embedding backend such as TEI with `BAAI/bge-m3`

# 1. Install `kb-index`

## 1.1 Local user installation

```bash
uv tool install .
```

The executable is normally placed under:

```text
~/.local/bin/kb-index
```

Ensure that `~/.local/bin` is in `PATH`, then check:

```bash
kb-index --help
```

To reinstall after changing the source:

```bash
uv tool install --force .
```

During development, you can also run it without installing:

```bash
uv run src/kb_index.py --shared examples
```

or, when the project script entry is configured:

```bash
uv run kb-index --shared examples
```

## 1.2 System-wide installation

Build the wheel as a normal user first:

```bash
rm -rf build dist src/*.egg-info
uv build
```

Install the wheel for all users:

```bash
sudo mkdir -p /opt/uv-tools /usr/local/bin

sudo env \
  UV_TOOL_DIR=/opt/uv-tools \
  UV_TOOL_BIN_DIR=/usr/local/bin \
  uv tool install --force dist/*.whl
```

Check the installation:

```bash
which kb-index
kb-index --help
```

Expected executable path:

```text
/usr/local/bin/kb-index
```

To uninstall:

```bash
sudo env \
  UV_TOOL_DIR=/opt/uv-tools \
  UV_TOOL_BIN_DIR=/usr/local/bin \
  uv tool uninstall filesystem-knowledge-bridge
```

The uninstall name is the package name from `pyproject.toml`, not necessarily the executable name.

# 2. Configure the CLI

`kb-index` reads the following environment variables:

```dotenv
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=

LITELLM_API_BASE=http://localhost:4000/v1
LITELLM_API_KEY=your-litellm-key
EMBEDDING_MODEL=lab-embedding

KNOWLEDGE_LOGICAL_ROOT=labknowledge://
```

When LiteLLM authentication uses one master key, set:

```bash
export LITELLM_API_KEY="$LITELLM_MASTER_KEY"
```

The host-side CLI must be able to reach both LiteLLM and Qdrant.

## Basic usage

```bash
kb-index --shared /path/to/project
kb-index /path/to/project
kb-index --owner alice /path/to/project
kb-index --project-id stable-project-id /path/to/project
kb-index --collection curated_project /path/to/project
kb-index --shared --dry-run /path/to/project
```

Default collection names:

```text
shared_<project-id>
private_<owner>_<project-id>
```

# 3. Build the complete system

The minimal runtime system consists of Open WebUI, LiteLLM, Qdrant, and TEI with BGE-M3. The indexer itself does not need to run continuously.

## 3.1 `.env`

```dotenv
COMPOSE_PROJECT_NAME=lab-ai

OPENWEBUI_PORT=3000
WEBUI_SECRET_KEY=replace-with-a-long-random-secret
ENABLE_SIGNUP=true
RAG_TOP_K=5

LITELLM_PORT=4000
LITELLM_MASTER_KEY=replace-with-a-strong-key

OPENAI_API_KEY=
GEMINI_API_KEY=
ANTHROPIC_API_KEY=

EMBEDDING_MODEL=lab-embedding

QDRANT_HTTP_PORT=6333
QDRANT_API_KEY=

KNOWLEDGE_LOGICAL_ROOT=labknowledge://
```

Do not commit `.env`.

```gitignore
.env
open-webui/
```

## 3.2 `docker-compose.yml`

```yaml
services:
  open-webui:
    image: ghcr.io/open-webui/open-webui:v0.10.2
    container_name: open-webui
    ports:
      - "${OPENWEBUI_PORT:-3000}:8080"
    volumes:
      - ./open-webui:/app/backend/data
    environment:
      OPENAI_API_BASE_URL: http://litellm:4000/v1
      OPENAI_API_KEY: ${LITELLM_MASTER_KEY}

      RAG_EMBEDDING_ENGINE: openai
      RAG_OPENAI_API_BASE_URL: http://litellm:4000/v1
      RAG_OPENAI_API_KEY: ${LITELLM_MASTER_KEY}
      RAG_EMBEDDING_MODEL: ${EMBEDDING_MODEL}
      RAG_TOP_K: ${RAG_TOP_K:-5}

      WEBUI_SECRET_KEY: ${WEBUI_SECRET_KEY}
      ENABLE_SIGNUP: ${ENABLE_SIGNUP:-true}
    depends_on:
      - litellm
      - qdrant
    restart: unless-stopped

  litellm:
    image: ghcr.io/berriai/litellm:main-latest
    container_name: litellm
    env_file:
      - .env
    volumes:
      - ./litellm/config.yaml:/app/config.yaml:ro
    command:
      - "--config=/app/config.yaml"
    ports:
      - "127.0.0.1:${LITELLM_PORT:-4000}:4000"
    restart: unless-stopped

  tei:
    image: ghcr.io/huggingface/text-embeddings-inference:latest
    container_name: tei
    command:
      - --model-id
      - BAAI/bge-m3
    volumes:
      - hf_cache:/data
    restart: unless-stopped

  qdrant:
    image: qdrant/qdrant:v1.17.0
    container_name: qdrant
    ports:
      - "127.0.0.1:${QDRANT_HTTP_PORT:-6333}:6333"
    volumes:
      - qdrant_data:/qdrant/storage
    restart: unless-stopped

volumes:
  qdrant_data:
  hf_cache:
```

Only Open WebUI needs to be exposed to users. LiteLLM and Qdrant are bound to localhost above only so that the host-side `kb-index` command can reach them. TEI is not exposed.

## 3.3 LiteLLM `config.yaml`

```yaml
model_list:
  - model_name: lab-embedding
    litellm_params:
      model: openai/BAAI/bge-m3
      api_base: http://tei:80/v1
      api_key: dummy
      mode: embedding
      encoding_format: float

general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
```

Add chat models to the same `model_list` as needed.

## 3.4 Start and verify

```bash
docker compose up -d
docker compose ps
```

```bash
curl http://localhost:4000/v1/models \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY"
```

```bash
curl http://localhost:4000/v1/embeddings \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "lab-embedding",
    "input": "test embedding",
    "encoding_format": "float"
  }'
```

```bash
curl http://localhost:6333/collections
```

# 4. Register a project

```bash
export QDRANT_URL=http://localhost:6333
export LITELLM_API_BASE=http://localhost:4000/v1
export LITELLM_API_KEY="$LITELLM_MASTER_KEY"
export EMBEDDING_MODEL=lab-embedding

kb-index --shared examples
```

The command scans supported files, chunks them, generates embeddings through LiteLLM, recreates the target collection, and stores Open WebUI-compatible payload fields.

Inspect one point:

```bash
curl http://localhost:6333/collections/shared_examples/points/scroll \
  -H "Content-Type: application/json" \
  -d '{
    "limit": 1,
    "with_payload": true,
    "with_vector": false
  }'
```

Expected fields:

```json
{
  "text": "chunk text",
  "metadata": {
    "scope": "shared",
    "owner": "shared",
    "project_id": "examples",
    "relative_path": "sample_project/docs/setup.md",
    "file_name": "setup.md",
    "chunk_index": 1
  }
}
```

# 5. Use the collection from Open WebUI

## 5.1 Confirm embedding settings

Open:

```text
Admin Panel
→ Settings
→ Documents
→ Embedding
```

Set:

```text
Embedding Model Engine: OpenAI
API Base URL: http://litellm:4000/v1
Embedding Model: lab-embedding
```

The Open WebUI query embedding model must match the model used by `kb-index`.

## 5.2 Add an External Knowledge Source

Open:

```text
Admin Panel
→ Settings
→ Integrations
→ External Knowledge Sources
→ Add Knowledge Connection
```

Example:

```text
Name: Curated Knowledge
Provider: Qdrant
Endpoint: http://qdrant:6333
API Key / Token: empty unless Qdrant authentication is enabled

Collection: shared_examples
Content Field: payload.text
Vector Field: default
Metadata Field: payload.metadata
Document ID Field: id
```

Enter a test query such as:

```text
Which Python version is required?
```

Confirm that Open WebUI displays `Test Succeeded`, then create the connection.

## 5.3 Use it in a chat

Attach the created knowledge connection to a model or chat and ask questions such as:

```text
Which Python version is required?
What does main.py do?
```

A successful setup should retrieve sources, answer from the indexed project, and display source references.

# Supported file types

- Markdown: `.md`, `.markdown`
- Plain and structured text: `.txt`, `.rst`, `.yaml`, `.yml`, `.json`, `.csv`, `.toml`, `.ini`, `.cfg`, `.tex`
- Source code: Python, JavaScript, TypeScript, Java, C/C++, C#, Go, Rust, Ruby, PHP
- Documents: PDF, DOCX, PPTX

# Design principles

- Reuse existing components whenever possible.
- Do not add a custom search server unless necessary.
- Keep indexing separate from retrieval.
- Preserve project structure and source metadata.
- Prefer complete replacement over premature incremental indexing.
- Keep the current working indexer stable before adding MCP or registration tools.

# License

MIT
