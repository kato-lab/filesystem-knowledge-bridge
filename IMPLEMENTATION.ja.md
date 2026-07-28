# v0.2.0 実装方針

v0.1.0の `kb_index.py` を登録処理の本体として維持し、二つのMCPサービスを追加した最小構成です。

## サービス

### knowledge-read-mcp（8000）

原本領域を読み取り専用でマウントします。

- `search_knowledge`
- `list_knowledge_projects`
- `read_knowledge_source`

### knowledge-register-mcp（8001）

incomingを読み取り専用、保護された原本領域を読み書き可能でマウントします。

- `list_incoming`
- `register_incoming_project`
- `reindex_stored_project`

`register_incoming_project` は `/incoming/users/<owner>/<project>/` を
`/knowledge/users/<owner>/<project>/` へコピーし、その後 `kb_index.index_directory()` を呼びます。

## 原本保全

- incomingを削除・移動しません。
- 保存済み原本を上書き・削除しません。
- 同名原本がある場合は登録を拒否します。
- QdrantのCollectionは従来どおり削除・再構築します。
- Qdrant登録失敗後は `reindex_stored_project` で再実行できます。

## 同時登録

登録は1プロセスにつき同時1件です。競合時は待機せずエラーを返します。

## 認証について

初期版は `X-Knowledge-Owner` または `X-OpenWebUI-User-Name` をowner識別に使います。
これは完全な認証ではありません。信頼できる内部ネットワークでのみ利用してください。
