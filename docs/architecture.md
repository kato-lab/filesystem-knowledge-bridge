# Architecture

```text
knowledge/ → indexer → Qdrant → MCP server → AI clients
```

## Design principles

- The filesystem is the source of truth.
- Qdrant is an index, not the original knowledge store.
- Path is first-class metadata.
- MCP exposes the same knowledge layer to multiple AI clients.
