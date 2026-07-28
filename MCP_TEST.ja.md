# MCP簡易・結合テスト

この手順では、Node.jsやMCP Inspectorを使用しません。
プロジェクトが依存しているMCP Python SDKを使い、`uv run`からRead MCPとRegister MCPを直接テストします。

## 0. 前提

- `docker-compose.yml.example`と同じディレクトリで実行する
- `.env`、LiteLLM設定、Qdrant、TEIが構成済み
- `pyproject.toml`に`[build-system]`がある
- `uv sync`済み、または`uv run`時に環境を構築できる
- MCPをlocalhostへ公開するテスト用Compose設定になっている

接続先の既定値:

```text
Read MCP:     http://localhost:8000/mcp
Register MCP: http://localhost:8001/mcp
```

MCPをDocker外へ公開しない本番構成では、このテスト時だけlocalhostへ公開するか、同じDockerネットワークにテスト用コンテナを置いて実行します。

---

## 1. MCPサービスだけをビルド・起動

Qdrant、TEI、LiteLLMがすでに動作中なら、それらを再ビルド・再起動する必要はありません。

```bash
docker compose -f docker-compose.yml.example up -d --build \
  knowledge-read-mcp knowledge-register-mcp
```

起動状態を確認します。

```bash
docker compose -f docker-compose.yml.example ps \
  knowledge-read-mcp knowledge-register-mcp
```

ログを確認します。

```bash
docker compose -f docker-compose.yml.example logs --tail=100 \
  knowledge-read-mcp knowledge-register-mcp
```

エラーで終了していないことを確認します。

---

## 2. Pythonテストクライアントの確認

ヘルプを表示します。

```bash
uv run python scripts/mcp_test.py --help
```

`mcp`依存はプロジェクト本体に含まれているため、Node.jsや`npx`の追加インストールは不要です。

---

## 3. MCP接続とTool一覧

```bash
uv run python scripts/mcp_test.py inspect
```

Read MCPで、次のToolが表示されることを確認します。

- `search_knowledge`
- `list_knowledge_projects`
- `read_knowledge_source`

Register MCPで、次のToolが表示されることを確認します。

- `list_incoming`
- `register_incoming_project`
- `reindex_stored_project`

最後に次が表示されれば合格です。

```text
MCP Tool一覧: OK
```

接続先が異なる場合:

```bash
uv run python scripts/mcp_test.py \
  --read-url http://server:8000/mcp \
  --register-url http://server:8001/mcp \
  inspect
```

---

## 4. incomingへテストプロジェクトを配置

現在の初期版は、ZIPではなく展開済みフォルダをincomingへ配置します。

```bash
sudo mkdir -p /mnt/knowledge-incoming/users/alice/sample-project
sudo cp -a examples/. /mnt/knowledge-incoming/users/alice/sample-project/
```

必要に応じて、Register MCPコンテナから読み取れる所有者・権限へ調整します。

```bash
sudo chmod -R a+rX /mnt/knowledge-incoming/users/alice/sample-project
```

incoming候補をMCP経由で確認します。

```bash
uv run python scripts/mcp_test.py incoming --owner alice
```

結果に`sample-project`が含まれることを確認します。

ホスト側でも確認します。

```bash
test -d /mnt/knowledge-incoming/users/alice/sample-project
```

---

## 5. incomingプロジェクトを登録

```bash
uv run python scripts/mcp_test.py register \
  --owner alice \
  --project sample-project
```

処理内容:

```text
/incoming/users/alice/sample-project/
    ↓ コピー（incomingは残す）
/knowledge/users/alice/sample-project/
    ↓
private_alice_sample-project Collectionを作成
```

登録後、原本が両方に存在することを確認します。

```bash
test -d /mnt/knowledge-incoming/users/alice/sample-project
test -d /mnt/knowledge/users/alice/sample-project
```

Qdrant Collectionを確認します。

```bash
curl -fsS \
  http://localhost:6333/collections/private_alice_sample-project
```

`status`が`green`であること、またはCollection情報が正常に返ることを確認します。

### 同名原本の上書き拒否も同時に確認する場合

最初の登録時に次を使用します。

```bash
uv run python scripts/mcp_test.py register \
  --owner alice \
  --project sample-project \
  --check-duplicate
```

最初の登録が成功し、直後の2回目がエラーになると、最後に次が表示されます。

```text
同名原本の再登録拒否: OK
```

すでに登録済みの場合は、`register`ではなく次節の`reindex`を使用してください。

---

## 6. 保存済み原本から再インデックス

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

Collectionを再確認します。

```bash
curl -fsS \
  http://localhost:6333/collections/private_alice_sample-project
```

---

## 7. Read MCPからプロジェクト一覧を確認

```bash
uv run python scripts/mcp_test.py projects --owner alice
```

結果に次が含まれることを確認します。

```text
private_alice_sample-project
```

共有Knowledgeが登録済みなら、共有プロジェクトも表示されます。

---

## 8. Read MCPから検索

`examples`内に含まれる語句を指定します。例えばREADMEやサンプル文書に`Python`が含まれる場合:

```bash
uv run python scripts/mcp_test.py search \
  "Python" \
  --owner alice \
  --project sample-project \
  --limit 5
```

確認項目:

- 結果が最大5件である
- `project_id`またはproject情報が`sample-project`である
- `relative_path`、`text`、`score`が返る
- 他ユーザーの個人Collectionが含まれない

プロジェクトを指定しない横断検索:

```bash
uv run python scripts/mcp_test.py search \
  "Python" \
  --owner alice \
  --limit 5
```

`limit`は各Collectionの件数ではなく、統合後の最終件数です。

---

## 9. 原本参照

`read_knowledge_source`は、検索結果だけでは前後関係が不足する場合に使います。

現テストスクリプトは誤ったパスを手入力しないよう、原本参照の自動実行を行いません。まず検索結果から次を確認します。

- `scope`
- `project`
- `relative_path`
- 個人Knowledgeの場合は`owner`

MCPクライアントやOpen WebUIから、その値を使って`read_knowledge_source`を呼び出します。

例:

```json
{
  "scope": "private",
  "owner": "alice",
  "project": "sample-project",
  "relative_path": "README.md",
  "start_line": 1,
  "max_lines": 100
}
```

確認項目:

- 指定した範囲だけ返る
- 原本が変更されない
- `../`など許可領域外のパスが拒否される
- PDF、DOCX、PPTXなど初期版で未対応の原本形式が拒否される

---

## 10. 異常時の切り分け

### 接続できない

```bash
docker compose -f docker-compose.yml.example ps \
  knowledge-read-mcp knowledge-register-mcp

docker compose -f docker-compose.yml.example logs --tail=200 \
  knowledge-read-mcp knowledge-register-mcp
```

ホスト公開を確認します。

```bash
ss -lnt | grep -E ':8000|:8001'
```

### `kb-read-mcp`が見つからない

コンテナ内のCLIを確認します。

```bash
docker compose -f docker-compose.yml.example run --rm \
  --entrypoint sh knowledge-read-mcp \
  -lc 'ls -l /app/.venv/bin/kb-*'
```

`pyproject.toml`の`[project.scripts]`と`[build-system]`、Dockerfileの`uv sync`を確認して再ビルドします。

### Tool呼び出しは成功するが登録できない

Register MCPのログを確認します。

```bash
docker compose -f docker-compose.yml.example logs --tail=200 \
  knowledge-register-mcp
```

続けて、コンテナからincomingと原本領域を確認します。

```bash
docker compose -f docker-compose.yml.example exec \
  knowledge-register-mcp \
  sh -lc 'find /incoming/users -maxdepth 3 -type d; find /knowledge/users -maxdepth 3 -type d'
```

LiteLLMとQdrantの疎通も確認します。

```bash
curl -fsS http://localhost:4000/v1/models \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY"

curl -fsS http://localhost:6333/collections
```

---

## 11. テスト後の扱い

初期版では、原本を自動削除しません。

- incoming原本は残る
- 保存済み原本は残る
- Qdrant Collectionだけは再構築される

テストデータを削除する場合は、Web登録を停止したうえで、管理者が明示的に作業してください。削除操作は初期版MCPの対象外です。
