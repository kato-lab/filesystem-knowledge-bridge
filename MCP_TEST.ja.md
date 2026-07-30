# MCP簡易・結合テスト

この手順では、Node.jsやMCP Inspectorを使用しません。プロジェクトが依存しているMCP Python SDKと `scripts/mcp_test.py` を使い、Read MCPとRegister MCPを直接確認します。

この手順の目的は、既存の登録・検索処理そのものの単体確認ではなく、次の経路が結合して動くことを確認することです。

```text
mcp_test.py
  ├─ Read MCP     → Qdrant検索・原本参照
  └─ Register MCP → incoming取込・kb_indexによる登録
```

管理者向けCLIの確認は、必要に応じて別途 `kb-index` と `kb-search` で行ってください。

---

## 0. 前提

- `docker-compose.yml.example` と同じディレクトリで実行する
- `.env`、LiteLLM、Qdrant、Embeddingサーバが構成済み
- `pyproject.toml` に `[build-system]` がある
- `uv sync` 済み、または `uv run` で環境を構築できる
- テスト時はMCPをlocalhostへ公開している

既定の接続先:

```text
Read MCP:     http://localhost:8000/mcp
Register MCP: http://localhost:8001/mcp
```

本番でMCPをDocker外へ公開しない場合は、テスト時だけlocalhostへ公開するか、同じDockerネットワーク上のテスト用コンテナから実行します。

---

## 1. MCPサービスをビルド・起動

Qdrant、Embeddingサーバ、LiteLLMがすでに動作中なら、MCPサービスだけをビルド・起動します。

```bash
docker compose -f docker-compose.yml.example up -d --build \
  knowledge-read-mcp knowledge-register-mcp
```

状態とログを確認します。

```bash
docker compose -f docker-compose.yml.example ps \
  knowledge-read-mcp knowledge-register-mcp

docker compose -f docker-compose.yml.example logs --tail=100 \
  knowledge-read-mcp knowledge-register-mcp
```

次のように待受状態になっていれば起動成功です。

```text
Read MCP:     Uvicorn running on http://0.0.0.0:8000
Register MCP: Uvicorn running on http://0.0.0.0:8001
```

単純な `curl http://localhost:8000/mcp` では、MCPクライアントに必要なAcceptヘッダーがないため `406 Not Acceptable` が返ることがあります。接続確認は次節の `inspect` を正とします。

---

## 2. テストクライアントの確認

```bash
uv run python scripts/mcp_test.py --help
```

コマンドは次の3系統です。

```text
Utility
  inspect

Read MCP
  projects
  search
  read

Register MCP
  incoming
  register
  reindex
```

接続先が異なる場合は、共通オプションで変更できます。

```bash
uv run python scripts/mcp_test.py \
  --read-url http://server:8000/mcp \
  --register-url http://server:8001/mcp \
  inspect
```

---

## 3. MCP接続とTool一覧

```bash
uv run python scripts/mcp_test.py inspect
```

Read MCP:

- `search_knowledge`
- `list_knowledge_projects`
- `read_knowledge_source`

Register MCP:

- `list_incoming`
- `register_incoming_project`
- `reindex_stored_project`

最後に次が表示されれば合格です。

```text
MCP Tool一覧: OK
```

---

## 4. incomingへテストプロジェクトを配置

初期版では、ZIPではなく展開済みフォルダを配置します。

以下はownerを `alice` とする例です。

```bash
mkdir -p /mnt/knowledge-incoming/users/alice/sample-project
cp -a examples/sample_project/. \
  /mnt/knowledge-incoming/users/alice/sample-project/
chmod -R a+rX /mnt/knowledge-incoming/users/alice/sample-project
```

ディレクトリ名は `users` です。

```text
/mnt/knowledge-incoming/users/<owner>/<project>/
```

Register MCPから候補を確認します。

```bash
uv run python scripts/mcp_test.py incoming --owner alice
```

結果に `sample-project` が含まれることを確認します。

---

## 5. Register MCP経由で登録

```bash
uv run python scripts/mcp_test.py register \
  --owner alice \
  --project sample-project
```

処理の流れ:

```text
/incoming/users/alice/sample-project/
    ↓ コピー（incomingは残す）
/knowledge/users/alice/sample-project/
    ↓ kb_index.index_directory()
private_alice_sample-project Collectionを作成
```

正常時は、概ね次の情報が返ります。

```json
{
  "status": "completed",
  "source_preserved": true,
  "stored_path": "/knowledge/users/alice/sample-project",
  "collection": "private_alice_sample-project",
  "nodes": 6
}
```

原本が両方に存在することを確認します。

```bash
test -d /mnt/knowledge-incoming/users/alice/sample-project
test -d /mnt/knowledge/users/alice/sample-project
```

Qdrant Collectionを確認します。

```bash
curl -fsS \
  http://localhost:6333/collections/private_alice_sample-project
```

---

## 6. Read MCPからプロジェクト一覧を確認

```bash
uv run python scripts/mcp_test.py projects --owner alice
```

少なくとも次が含まれることを確認します。

```text
private_alice_sample-project
```

共有Knowledgeが登録済みなら、共有プロジェクトも同時に表示されます。

---

## 7. Read MCPから検索

```bash
uv run python scripts/mcp_test.py search \
  "Python" \
  --owner alice \
  --project sample-project \
  --limit 5
```

確認項目:

- 結果が最大5件
- `collection` が `private_alice_sample-project`
- `project_id` が `sample-project`
- `relative_path`、`text`、`score` が返る
- 他ユーザーの個人Collectionが混ざらない
- `logical_path` が `labknowledge://users/...` の形式

期待例:

```text
labknowledge://users/alice/sample-project/src/main.py
```

プロジェクトを指定しない横断検索:

```bash
uv run python scripts/mcp_test.py search \
  "Python" \
  --owner alice \
  --limit 5
```

`limit` は各Collectionごとの件数ではなく、統合後の最終件数です。

---

## 8. 検索結果から原本を参照

検索結果の `scope`、`project_id`、`relative_path` を使います。

個人Knowledgeの例:

```bash
uv run python scripts/mcp_test.py read \
  --scope personal \
  --owner alice \
  --project sample-project \
  --path src/main.py \
  --start-line 1 \
  --max-lines 50
```

共有Knowledgeの例:

```bash
uv run python scripts/mcp_test.py read \
  --scope shared \
  --project examples \
  --path README.md \
  --start-line 1 \
  --max-lines 50
```

確認項目:

- 指定したファイル内容が行番号付きで返る
- `start-line` と `max-lines` が反映される
- 個人Knowledgeではowner指定が必要
- project外のパスや `../` を使った参照が拒否される

原本参照は、検索チャンクだけでは前後関係が不足する場合に限定して使うことを想定しています。

---

## 9. 保存済み原本から再インデックス

原本を変更せず、Qdrant Collectionだけを削除・再構築します。

```bash
uv run python scripts/mcp_test.py reindex \
  --owner alice \
  --project sample-project
```

再実行後も原本が残っていることを確認します。

```bash
test -d /mnt/knowledge/users/alice/sample-project
```

---

## 10. 同名原本の自動上書き拒否

すでに登録済みのprojectへ、再度 `register` を実行します。

```bash
uv run python scripts/mcp_test.py register \
  --owner alice \
  --project sample-project
```

保存済み原本を上書きせず、Toolがエラーを返すことを確認します。

新規projectの初回登録と直後の拒否をまとめて確認する場合は、初回登録時に次を使います。

```bash
uv run python scripts/mcp_test.py register \
  --owner alice \
  --project another-project \
  --check-duplicate
```

成功時:

```text
同名原本の再登録拒否: OK
```

---

## 11. 合格条件

- Read MCPとRegister MCPへ接続できる
- 想定したTool一覧を取得できる
- incoming候補を取得できる
- Register MCP経由で原本コピーとCollection作成が成功する
- incoming原本が削除されない
- Read MCPで共有＋本人の個人プロジェクトを一覧表示できる
- projectを限定して検索できる
- `logical_path` が `labknowledge://...` 形式で返る
- 検索結果の相対パスから原本を範囲指定で参照できる
- 保存済み原本から再インデックスできる
- 同名原本を自動上書きしない

## UUID project_id の確認

新規登録結果で、`project`が指定した表示名のまま、`project_id`がUUIDになっていることを確認します。

```text
project:    引き継ぎ資料_2025年度_アリス
project_id: 0c596ad3-4eb4-4699-ae14-f6e2e5c59c7d
```

保存済み原本の `.kb_project.json` も確認します。

```bash
cat '/mnt/knowledge/users/alice/引き継ぎ資料_2025年度_アリス/.kb_project.json'
```

再インデックス後も同じ`project_id`とCollection名が返ることを確認してください。
