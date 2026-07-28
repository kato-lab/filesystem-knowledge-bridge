# filesystem-knowledge-bridge

**filesystem-knowledge-bridge** is a lightweight knowledge indexing and retrieval tool that registers frozen project folders as **Qdrant Collections** and makes them searchable and readable through CLI and MCP.

> A **frozen project** is a project whose development or editing has reached a stable point and whose contents have been fixed as a specific version. This tool is designed to register and manage such projects as searchable knowledge.

It indexes source code, Markdown, PDF, and Office documents on a per-project basis. Search results can optionally lead to the original source files, making the tool suitable as a knowledge backend for AI agents and chat systems.

The project focuses on knowledge registration, search, and source access, and does not depend on a particular UI such as Open WebUI.

## Features

- One Qdrant Collection per project
- Shared and personal knowledge scopes
- Administrator indexing with `kb-index`
- CLI search with `kb-search`
- Read MCP for search, project listing, and source access
- Register MCP for importing pre-staged projects and rebuilding indexes
- Original files remain on the filesystem rather than being stored in Qdrant

## Architecture

The same Python package and Docker image are used to run two separate MCP services:

- **Read MCP**: search, listing, and cautious source access
- **Register MCP**: import from an incoming directory and rebuild indexes

## Collection names

```text
Shared:   shared_<project-id>
Personal: private_<owner>_<project-id>
```

The initial version does not implement authentication or verify that an owner value belongs to the caller. Expose MCP endpoints only on localhost or a trusted internal network.

## Installation

After cloning the repository, synchronize the project environment:

```bash
uv sync
```

Run the CLI commands through `uv run`:

```bash
uv run kb-index --help
uv run kb-search --help
```

Use `uv add` when adding dependencies instead of editing `pyproject.toml` manually:

```bash
uv add <package-name>
```

## Environment

```dotenv
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
LITELLM_API_BASE=http://localhost:4000/v1
LITELLM_API_KEY=
EMBEDDING_MODEL=lab-embedding
KNOWLEDGE_LOGICAL_ROOT=labknowledge://
```

Use the same embedding model for indexing and search.

## Indexing with CLI

Shared knowledge:

```bash
kb-index --shared /path/to/project
```

Personal knowledge:

```bash
kb-index --owner alice /path/to/project
```

Re-indexing deletes and rebuilds the Qdrant Collection. It does not modify or delete the source files.

## Searching with CLI

```bash
kb-search --owner alice "MCP server design"
```

Limit search to a project:

```bash
kb-search --owner alice \
  --project filesystem-knowledge-bridge \
  "registration"
```

## Docker Compose

Configure the host directories in `.env`:

```dotenv
KNOWLEDGE_HOST_ROOT=/mnt/knowledge
KNOWLEDGE_INCOMING_HOST_ROOT=/mnt/knowledge-incoming
```

Build and start only the MCP services:

```bash
docker compose -f docker-compose.yml.example up -d --build \
  knowledge-read-mcp knowledge-register-mcp
```

Endpoints:

```text
Read MCP:     http://localhost:8000/mcp
Register MCP: http://localhost:8001/mcp
```

## Read MCP tools

- `search_knowledge`
- `list_knowledge_projects`
- `read_knowledge_source`

The search tool searches shared Collections and, when an owner is supplied, that owner's personal Collections. When projects are omitted, results are merged across the allowed Collections and only the overall top results are returned.

Source access is a separate, explicit operation. Search does not automatically return entire source files.

## Register MCP tools

- `list_incoming`
- `register_incoming_project`
- `reindex_stored_project`

Place projects in:

```text
/incoming/users/<owner>/<project>/
```

Registration copies a project to:

```text
/knowledge/users/<owner>/<project>/
```

The register service follows these rules:

- It never deletes or moves the incoming source
- It never overwrites an existing stored source automatically
- It returns an error when the destination already exists
- Only one registration runs at a time
- Stored source files remain after an indexing failure

## Source directories

```text
/knowledge/
├── shared/<project>/
└── users/<owner>/<project>/

/incoming/
└── users/<owner>/<project>/
```

The Read MCP mounts `/knowledge` read-only. The Register MCP has write access to `/knowledge` and read-only access to `/incoming`.

## Testing

See [MCP_TEST.ja.md](MCP_TEST.ja.md).

## License

MIT License
