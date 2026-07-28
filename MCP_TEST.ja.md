# MCPサービス確認手順

## 1. 準備

```bash
cp .env.example .env
```

`.env`の接続先、APIキー、ホスト側ディレクトリを設定します。

```dotenv
KNOWLEDGE_HOST_PATH=/mnt/knowledge
INCOMING_HOST_PATH=/mnt/knowledge-incoming
LITELLM_MASTER_KEY=...
EMBEDDING_MODEL=lab-embedding
```

テスト用プロジェクトを配置します。

```bash
mkdir -p /mnt/knowledge-incoming/users/alice/sample-project
cp -a examples/sample_project/. \
  /mnt/knowledge-incoming/users/alice/sample-project/
```

## 2. 起動

```bash
docker compose -f docker-compose.yml.example up -d --build \
  qdrant tei litellm knowledge-read-mcp knowledge-register-mcp

docker compose -f docker-compose.yml.example ps
```

ログ確認：

```bash
docker compose -f docker-compose.yml.example logs --tail=100 knowledge-read-mcp
docker compose -f docker-compose.yml.example logs --tail=100 knowledge-register-mcp
```

## 3. MCP Inspectorで登録MCPを確認

MCP InspectorなどのStreamable HTTP対応クライアントから接続します。

```text
URL: http://127.0.0.1:8001/mcp
Header: X-Knowledge-Owner: alice
```

順に実行します。

1. `list_incoming`
2. `register_incoming_project(project="sample-project")`
3. `reindex_stored_project(project="sample-project")`

合格条件：

- `list_incoming`に`sample-project`が出る
- `/mnt/knowledge-incoming/...`が削除されない
- `/mnt/knowledge/users/alice/sample-project/`が作成される
- `private_alice_sample-project` Collectionが作成される
- 同じ`register_incoming_project`の再実行は、原本を上書きせずエラーになる
- `reindex_stored_project`はQdrantを再構築できる

## 4. 読み取りMCPを確認

```text
URL: http://127.0.0.1:8000/mcp
Header: X-Knowledge-Owner: alice
```

順に実行します。

1. `list_knowledge_projects`
2. `search_knowledge(query="sample project", projects=["sample-project"])`
3. 検索結果の`source_ref`を使って`read_knowledge_source`

合格条件：

- 共有Collectionとalice本人の個人Collectionだけが一覧に出る
- 検索結果は全Collection合計で`limit`件以内
- `read_knowledge_source`はテキスト系原本の指定範囲だけ返す
- 他ユーザーの`source_ref`は拒否される

## 5. 原本マウント権限の確認

読み取りMCPから書き込みできないことを確認します。

```bash
docker compose -f docker-compose.yml.example exec knowledge-read-mcp \
  sh -c 'touch /knowledge/write-test'
```

失敗すれば正常です。

登録MCPでは、incomingは読み取り専用、原本保存領域は読み書き可能です。

```bash
docker compose -f docker-compose.yml.example exec knowledge-register-mcp \
  sh -c 'touch /incoming/write-test'
```

これも失敗すれば正常です。
