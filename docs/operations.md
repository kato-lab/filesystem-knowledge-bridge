# Operations

## Start Qdrant

```bash
docker compose up -d qdrant
```

## Index files

```bash
docker compose run --rm indexer
```

## Search

```bash
docker compose run --rm search "experiment condition"
```

## Start MCP server

```bash
docker compose up -d mcp
```

## Logs

```bash
docker compose logs -f mcp
```
