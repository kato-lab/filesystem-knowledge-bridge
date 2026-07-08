# filesystem-knowledge-bridge

既存のフォルダ構造をそのままAI Knowledgeとして使うための小さなBridge実装です。

このリポジトリは、OpenWebUI + LiteLLM による研究室AI基盤の記事シリーズの補助実装として作成しています。

目的は、新しいRAGチャットアプリを作ることではありません。既存のファイルスペースをKnowledgeの本体として残し、Qdrant / LlamaIndex / MCP を使ってAIから参照できるようにすることです。

## Concept

```text
/home/<user>/knowledge
/home/share/knowledge
または
./knowledge

        ↓

filesystem-knowledge-bridge

        ↓

Qdrant + LlamaIndex

        ↓

MCP Server

        ↓

OpenWebUI / VSCode Agent / Cursor
```

## 作るもの・作らないもの

### 作るもの

- フォルダを再帰的に読み込むindexer
- ファイルパスをmetadataとして保持する仕組み
- Qdrantへの登録
- 検索確認コマンド
- MCP Server
- 最小限のKnowledge Admin API

### 作らないもの

- Chat UI
- LLM Gateway
- Vector DBそのもの
- Agentそのもの
- 本格的なDMS

## Quick start: simple mode

まずはリポジトリ内の `knowledge/` を使って試します。

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

## Laboratory mode: /home/<user>/knowledge

研究室運用では、各ユーザのホームディレクトリにKnowledgeフォルダを置くことを想定しています。

```text
/home/alice/knowledge
/home/bob/knowledge
/home/share/knowledge
```

`/home/<user>` が autofs + NFS の場合は、Docker bind mount に mount propagation が必要になることがあります。

```yaml
volumes:
  - type: bind
    source: /home
    target: /host_home
    read_only: true
    bind:
      propagation: rslave
```

コンテナ内では以下のように見えます。

```text
/host_home/alice/knowledge
/host_home/bob/knowledge
/host_home/share/knowledge
```

## SSO / reverse proxy integration

本アプリはユーザ管理を作り込みません。

本番運用では、authentik などのSSOとリバースプロキシを前段に置き、認証済みユーザ名をHTTPヘッダで渡す構成を想定しています。

```text
browser
  ↓
authentik
  ↓
reverse proxy
  ↓
X-authentik-username: alice
  ↓
knowledge-admin
  ↓
/host_home/alice/knowledge を更新
```

詳細は `docs/sso.md` を参照してください。

## Metadata

例:

```text
knowledge/projects/sample_project/experiments/2026-07-08.md
```

は、以下のようなmetadataとして登録されます。

```json
{
  "source_path": "projects/sample_project/experiments/2026-07-08.md",
  "top_dir": "projects",
  "project": "sample_project",
  "type": "experiment_log",
  "owner": "default"
}
```

## Status

Experimental. まずは「記事の補助コード」として小さく公開する想定です。
