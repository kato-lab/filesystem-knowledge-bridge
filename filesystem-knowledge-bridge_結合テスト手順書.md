# filesystem-knowledge-bridge v0.2.0 結合テスト手順書

## 1. 目的

本手順書は、`filesystem-knowledge-bridge v0.2.0` 実装案について、次の構成要素が連携して動作することを確認するためのものです。

- TEIによるEmbedding生成
- LiteLLMのOpenAI互換Embedding API
- QdrantへのKnowledge登録・検索
- ホストCLIの`kb-index`・`kb-search`
- `knowledge-bridge`コンテナのMCPサーバ
- Open WebUIからのKnowledge検索
- Open WebUI登録専用モデルからの個人Knowledge登録
- 必要時のみ行う原本参照
- 共有Knowledgeと個人Knowledgeの分離
- 登録中の同時実行拒否
- 原本領域がMCPサーバから読み取り専用であること

初期版では、チャット添付ZIPの展開・配置、アップロードAPI、原本の移動・上書き・削除は対象外です。

---

## 2. テスト方針

問題発生時に原因箇所を切り分けやすくするため、次の順に確認します。

```text
1. 単体テスト・ビルド
2. TEI・LiteLLM・Qdrantの疎通
3. ホストCLIからの共有・個人Knowledge登録
4. kb-searchによる検索
5. MCPサーバの起動とTool確認
6. MCP経由の検索・一覧・原本参照
7. MCP経由の個人Knowledge登録
8. Open WebUIとの接続
9. ユーザー分離・異常系
```

Open WebUIまで一度に接続せず、CLIとMCPを先に確認してください。

---

## 3. 前提環境

### 3.1 必要なソフトウェア

- Linuxホスト
- Docker Engine
- Docker Compose v2
- NVIDIA GPUおよびNVIDIA Container Toolkit
- Python 3.11以降
- `uv`
- `curl`
- 任意で`jq`

確認例：

```bash
docker --version
docker compose version
nvidia-smi
uv --version
python3 --version
```

### 3.2 テスト対象ファイル

展開後の構成を次とします。

```text
filesystem-knowledge-bridge-0.2.0/
├── docker-compose.yml.example
├── .env.example
├── litellm/config.yaml.example
├── Dockerfile
├── pyproject.toml
├── src/
└── tests/
```

以下では、このディレクトリへ移動済みとします。

```bash
cd filesystem-knowledge-bridge-0.2.0
```

---

## 4. テスト用Knowledgeの準備

ホスト上に共有Knowledgeと2ユーザー分の個人Knowledgeを作成します。

```bash
mkdir -p knowledge/shared/shared-sample/docs
mkdir -p knowledge/users/alice/personal-sample/src
mkdir -p knowledge/users/bob/bob-sample
```

共有Knowledge：

```bash
cat > knowledge/shared/shared-sample/README.md <<'EOF_SHARED'
# Shared Sample

このプロジェクトは研究室共通のナレッジです。
共通サーバのバックアップは毎週日曜日の午前3時に実行します。
EOF_SHARED

cat > knowledge/shared/shared-sample/docs/setup.md <<'EOF_SHARED_SETUP'
# セットアップ

Python 3.11以降を使用します。
EmbeddingモデルにはBAAI/bge-m3を使用します。
EOF_SHARED_SETUP
```

Aliceの個人Knowledge：

```bash
cat > knowledge/users/alice/personal-sample/README.md <<'EOF_ALICE'
# Alice Personal Sample

Aliceの実験ではセンサーのサンプリング周期を100ミリ秒に設定した。
EOF_ALICE

cat > knowledge/users/alice/personal-sample/src/config.py <<'EOF_ALICE_CODE'
SAMPLE_INTERVAL_MS = 100
RETRY_COUNT = 3


def build_config():
    return {
        "sample_interval_ms": SAMPLE_INTERVAL_MS,
        "retry_count": RETRY_COUNT,
    }
EOF_ALICE_CODE
```

Bobの個人Knowledge：

```bash
cat > knowledge/users/bob/bob-sample/README.md <<'EOF_BOB'
# Bob Personal Sample

Bobの実験では非公開パラメータとして閾値を0.73に設定した。
EOF_BOB
```

確認：

```bash
find knowledge -type f -maxdepth 5 -print
```

期待結果：

```text
knowledge/shared/shared-sample/README.md
knowledge/shared/shared-sample/docs/setup.md
knowledge/users/alice/personal-sample/README.md
knowledge/users/alice/personal-sample/src/config.py
knowledge/users/bob/bob-sample/README.md
```

---

## 5. 設定ファイルの準備

### 5.1 `.env`

```bash
cp .env.example .env
```

最低限、次を変更します。

```dotenv
WEBUI_SECRET_KEY=十分に長いランダム文字列
LITELLM_MASTER_KEY=十分に強いキー
EMBEDDING_MODEL=lab-embedding
KNOWLEDGE_HOST_ROOT=./knowledge
```

`KNOWLEDGE_HOST_ROOT`は`.env.example`に存在しない場合があるため、末尾に追加してください。

```bash
cat >> .env <<'EOF_ENV'
KNOWLEDGE_HOST_ROOT=./knowledge
EOF_ENV
```

### 5.2 LiteLLM設定

```bash
mkdir -p litellm
cp litellm/config.yaml.example litellm/config.yaml
```

### 5.3 Docker Compose設定

```bash
cp docker-compose.yml.example docker-compose.yml
```

Open WebUIからMCPへユーザー情報を転送するため、`open-webui.environment`へ次を追加します。

```yaml
ENABLE_FORWARD_USER_INFO_HEADERS: "true"
```

例：

```yaml
services:
  open-webui:
    environment:
      ENABLE_FORWARD_USER_INFO_HEADERS: "true"
```

### 5.4 Compose設定確認

```bash
docker compose config >/tmp/fkb-compose-resolved.yml
```

エラーが出ないことを確認します。

Knowledgeのマウントも確認します。

```bash
grep -A5 -B5 '/knowledge:ro' /tmp/fkb-compose-resolved.yml
```

---

## 6. Python単体テストとビルド確認

### 6.1 依存関係の同期

```bash
uv sync
```

### 6.2 テスト

```bash
uv run pytest -q
```

期待結果：

```text
5 passed
```

テスト数は改修により変わる場合があります。失敗がないことを確認してください。

### 6.3 パッケージビルド

```bash
rm -rf build dist src/*.egg-info
uv build
```

期待結果：

```text
dist/filesystem_knowledge_bridge-0.2.0-py3-none-any.whl
```

---

## 7. Dockerサービスの起動

### 7.1 起動

```bash
docker compose up -d --build
```

### 7.2 状態確認

```bash
docker compose ps
```

期待するサービス：

```text
open-webui
litellm
tei
qdrant
knowledge-bridge
```

すべて`Up`または`running`になっていることを確認します。

### 7.3 ログ確認

```bash
docker compose logs --tail=100 tei
docker compose logs --tail=100 litellm
docker compose logs --tail=100 qdrant
docker compose logs --tail=100 knowledge-bridge
```

初回はTEIがモデルをダウンロードするため、起動に時間がかかる場合があります。

---

## 8. 基盤サービスの疎通確認

### 8.1 Qdrant

```bash
curl -s http://localhost:6333/collections | jq .
```

`jq`がない場合：

```bash
curl http://localhost:6333/collections
```

期待結果：HTTP 200でCollection一覧が返る。

### 8.2 LiteLLMモデル一覧

```bash
set -a
source .env
set +a

curl -s http://localhost:4000/v1/models \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" | jq .
```

期待結果：`lab-embedding`が含まれる。

### 8.3 Embedding生成

```bash
curl -s http://localhost:4000/v1/embeddings \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "lab-embedding",
    "input": "結合テスト用の文章",
    "encoding_format": "float"
  }' | jq '.data[0].embedding | length'
```

期待結果：0より大きいベクトル次元が返る。

BGE-M3では通常1024次元ですが、テストでは固定値より「正常に配列が返ること」を重視します。

---

## 9. ホストCLIの準備

テスト中はインストールせず、`uv run`で実行できます。

```bash
uv run kb-index --help
uv run kb-search --help
```

環境変数を設定します。

```bash
export QDRANT_URL=http://localhost:6333
export QDRANT_API_KEY="${QDRANT_API_KEY:-}"
export LITELLM_API_BASE=http://localhost:4000/v1
export LITELLM_API_KEY="$LITELLM_MASTER_KEY"
export EMBEDDING_MODEL=lab-embedding
export KNOWLEDGE_LOGICAL_ROOT=labknowledge://
export KNOWLEDGE_ROOT="$(pwd)/knowledge"
```

---

## 10. `kb-index`による登録テスト

### 10.1 dry-run

```bash
uv run kb-index --shared --dry-run knowledge/shared/shared-sample
```

期待結果：

- nodeが生成される
- metadataに次が含まれる
  - `scope=shared`
  - `project_id=shared-sample`
  - `relative_path`
  - `logical_path`
  - `source_ref`
- Qdrant Collectionは作成されない

### 10.2 共有Knowledge登録

```bash
uv run kb-index --shared knowledge/shared/shared-sample
```

期待結果：

```text
登録完了: shared_shared-sample
```

### 10.3 Aliceの個人Knowledge登録

```bash
uv run kb-index --owner alice knowledge/users/alice/personal-sample
```

期待結果：

```text
登録完了: private_alice_personal-sample
```

### 10.4 Bobの個人Knowledge登録

```bash
uv run kb-index --owner bob knowledge/users/bob/bob-sample
```

期待結果：

```text
登録完了: private_bob_bob-sample
```

### 10.5 Qdrant Collection確認

```bash
curl -s http://localhost:6333/collections | jq -r '.result.collections[].name' | sort
```

期待結果：

```text
private_alice_personal-sample
private_bob_bob-sample
shared_shared-sample
```

---

## 11. Qdrant payload確認

共有Collectionから1件取得します。

```bash
curl -s \
  -X POST http://localhost:6333/collections/shared_shared-sample/points/scroll \
  -H 'Content-Type: application/json' \
  -d '{
    "limit": 1,
    "with_payload": true,
    "with_vector": false
  }' | jq '.result.points[0].payload'
```

次の情報が確認できること：

- チャンク本文
- `project_id`
- `project_name`
- `scope`
- `owner`
- `relative_path`
- `logical_path`
- `source_ref`
- `chunk_index`

`source_ref`の例：

```text
kbsource://shared/shared-sample/docs/setup.md
```

個人Knowledgeでは次のような形式になります。

```text
kbsource://users/alice/personal-sample/src/config.py
```

---

## 12. `kb-search`結合テスト

### 12.1 共有Knowledge検索

```bash
uv run kb-search --owner alice \
  --project shared-sample \
  "バックアップは何時に実行しますか"
```

期待結果：

- `shared:shared-sample`が返る
- 「毎週日曜日の午前3時」に関連する本文が返る

### 12.2 Aliceの個人Knowledge検索

```bash
uv run kb-search --owner alice \
  --project personal-sample \
  "サンプリング周期はいくつですか"
```

期待結果：100ミリ秒に関連する結果が返る。

### 12.3 共有＋個人の横断検索

```bash
uv run kb-search --owner alice \
  "Embeddingモデルとサンプリング周期を探してください" \
  --limit 5
```

期待結果：

- 共有CollectionとAliceの個人Collectionが検索対象になる
- Bobの個人Collectionは結果に含まれない
- 最終結果数が最大5件である

### 12.4 ユーザー分離確認

```bash
uv run kb-search --owner alice \
  "閾値0.73" \
  --json
```

期待結果：Bobの個人Knowledgeは検索されないため、該当結果が返らない。

Bobとして検索：

```bash
uv run kb-search --owner bob \
  "閾値0.73" \
  --json
```

期待結果：`private_bob_bob-sample`の結果が返る。

### 12.5 JSON出力

```bash
uv run kb-search --owner alice \
  --project personal-sample \
  --json \
  "RETRY_COUNT" | jq .
```

期待結果：各検索結果に`logical_path`と`source_ref`が含まれる。

---

## 13. MCPサーバの疎通確認

Compose例ではMCPポートをホストへ公開していません。直接テストする間だけ、`knowledge-bridge`へ次を追加します。

```yaml
ports:
  - "127.0.0.1:8000:8000"
```

反映：

```bash
docker compose up -d knowledge-bridge
```

### 13.1 HTTPエンドポイント確認

```bash
curl -i http://localhost:8000/mcp
```

単純なGETではMCPプロトコル上のエラーやMethod Not Allowedになる場合がありますが、接続拒否ではなくHTTP応答が返ればサーバ到達性は確認できます。

ログ確認：

```bash
docker compose logs --tail=100 knowledge-bridge
```

### 13.2 MCP Inspectorの利用

Node.js環境がある場合、MCP Inspectorを使用するとToolを対話的に確認できます。

```bash
npx @modelcontextprotocol/inspector
```

Inspectorで接続先を次に設定します。

```text
http://localhost:8000/mcp
```

カスタムヘッダー：

```text
X-Knowledge-Owner: alice
```

確認するTool：

- `search_knowledge`
- `list_knowledge_projects`
- `read_knowledge_source`
- `index_personal_knowledge`

Inspectorのバージョンにより画面や起動オプションが異なる場合があります。その場合は利用中のMCPクライアントから同じ接続先とヘッダーを設定してください。

---

## 14. MCP Tool結合テスト

### 14.1 プロジェクト一覧

`list_knowledge_projects`を次の条件で実行します。

```json
{}
```

接続ヘッダー：

```text
X-Knowledge-Owner: alice
```

期待結果：

- `shared-sample`
- `personal-sample`

が含まれる。

次は含まれないこと：

- `bob-sample`

### 14.2 プロジェクト限定検索

`search_knowledge`：

```json
{
  "query": "サンプリング周期はいくつですか",
  "projects": ["personal-sample"],
  "limit": 5
}
```

期待結果：

- `personal-sample`だけが検索される
- 100ミリ秒に関連する結果が返る
- `source_ref`が返る

### 14.3 横断検索

```json
{
  "query": "Pythonのバージョンまたはサンプリング周期",
  "limit": 5
}
```

期待結果：

- `shared-sample`と`personal-sample`が候補になる
- Bobの個人Knowledgeは含まれない
- 返却件数は全Collection合計で最大5件

### 14.4 原本参照

前項の検索結果から`source_ref`を取得します。

例：

```text
kbsource://users/alice/personal-sample/src/config.py
```

`read_knowledge_source`：

```json
{
  "source_ref": "kbsource://users/alice/personal-sample/src/config.py",
  "start_line": 1,
  "max_lines": 20
}
```

期待結果：

- 行番号付きの原本が返る
- `SAMPLE_INTERVAL_MS = 100`が含まれる
- `total_lines`、`start_line`、`end_line`、`truncated`が返る

### 14.5 他ユーザー原本の参照拒否

Aliceのヘッダーで次を実行します。

```json
{
  "source_ref": "kbsource://users/bob/bob-sample/README.md",
  "start_line": 1,
  "max_lines": 20
}
```

期待結果：他ユーザーの個人ナレッジを参照できない旨のエラー。

### 14.6 非対応形式

PDFなどを登録している場合、その`source_ref`を`read_knowledge_source`へ渡します。

期待結果：初期版では原本参照非対応形式としてエラーが返る。検索チャンクは引き続き利用できる。

---

## 15. MCP経由の個人Knowledge登録

### 15.1 未登録プロジェクトの準備

```bash
mkdir -p knowledge/users/alice/mcp-register-sample
cat > knowledge/users/alice/mcp-register-sample/README.md <<'EOF_MCP_REG'
# MCP Register Sample

この文書はMCP経由の登録確認用です。
確認コードはMCP-REGISTER-2026です。
EOF_MCP_REG
```

`knowledge-bridge`は原本領域を読み取り専用でマウントしていますが、ホスト側で配置した新規ファイルはコンテナから読み取れます。

コンテナ内確認：

```bash
docker compose exec knowledge-bridge \
  ls -la /knowledge/users/alice/mcp-register-sample
```

### 15.2 登録Tool実行

接続ヘッダー：

```text
X-Knowledge-Owner: alice
```

`index_personal_knowledge`：

```json
{
  "project": "mcp-register-sample"
}
```

期待結果例：

```json
{
  "status": "completed",
  "scope": "personal",
  "owner": "alice",
  "project_id": "mcp-register-sample",
  "collection": "private_alice_mcp-register-sample",
  "source_modified": false
}
```

### 15.3 検索確認

```json
{
  "query": "MCP-REGISTER-2026",
  "projects": ["mcp-register-sample"]
}
```

期待結果：登録確認用文書が検索される。

### 15.4 原本非変更確認

ホスト側でハッシュを比較します。

```bash
sha256sum knowledge/users/alice/mcp-register-sample/README.md
```

再登録：

```json
{
  "project": "mcp-register-sample"
}
```

再度：

```bash
sha256sum knowledge/users/alice/mcp-register-sample/README.md
```

期待結果：ハッシュが変化しない。

さらに、登録前後でファイル一覧が変化していないことを確認します。

```bash
find knowledge/users/alice/mcp-register-sample -printf '%P\n' | sort
```

---

## 16. 登録同時実行テスト

登録処理は同時に1件だけ許可し、待ち行列には入れません。

小さいプロジェクトでは処理が早く競合を再現しにくいため、十分な数の文書を含むテストプロジェクトを用意します。

```bash
mkdir -p knowledge/users/alice/slow-register-sample
for i in $(seq -w 1 100); do
  cat > "knowledge/users/alice/slow-register-sample/doc-${i}.md" <<EOF_SLOW
# Document ${i}

登録競合テスト用の文書です。
識別子はSLOW-${i}です。
EOF_SLOW
done
```

2つのMCPクライアントまたはInspector画面から、ほぼ同時に次を実行します。

1件目：

```json
{
  "project": "slow-register-sample"
}
```

1件目の実行中に2件目：

```json
{
  "project": "mcp-register-sample"
}
```

期待結果：

- 1件目は登録を継続する
- 2件目は待たずに次の趣旨のエラーを返す

```text
別のナレッジを登録中です。しばらくしてから再度実行してください。
```

1件目終了後に2件目を再実行し、成功することを確認します。

注：現在のロックはMCPサーバプロセス内だけです。管理者用`kb-index`との同時実行は自動制御せず、Web登録を停止してからCLIを使用する運用とします。

---

## 17. 原本領域の読み取り専用確認

コンテナ内からテストファイル作成を試みます。

```bash
docker compose exec knowledge-bridge \
  sh -lc 'touch /knowledge/users/alice/should-not-be-created.txt'
```

期待結果：

```text
Read-only file system
```

ホスト側でもファイルが作成されていないことを確認します。

```bash
test ! -e knowledge/users/alice/should-not-be-created.txt \
  && echo 'OK: 原本領域は変更されていません'
```

このテストは初期版の重要な保証です。

---

## 18. Open WebUI接続テスト

### 18.1 Open WebUIへログイン

ブラウザで次を開きます。

```text
http://<ホスト名またはIP>:3000
```

Aliceに相当するユーザー名でテストユーザーを作成します。

初期版では、Open WebUIのユーザー名とKnowledge領域のアカウント名が一致する前提です。

```text
Open WebUI username: alice
Knowledge path: /knowledge/users/alice/
```

### 18.2 MCPサーバ追加

Open WebUIの管理画面またはWorkspaceのTool/MCP設定から、MCPサーバを追加します。

接続先：

```text
http://knowledge-bridge:8000/mcp
```

Docker内部から接続するため、`localhost`は使用しません。

接続後、次のToolが見えることを確認します。

- `search_knowledge`
- `list_knowledge_projects`
- `read_knowledge_source`
- `index_personal_knowledge`

Open WebUI v0.10.2の画面表記や設定場所は環境により異なる可能性があります。

### 18.3 ユーザー情報転送確認

`ENABLE_FORWARD_USER_INFO_HEADERS=true`が有効な状態で、Tool引数に`owner`を明示せず次を実行します。

会話例：

```text
利用可能なナレッジプロジェクトを一覧表示してください。
```

期待結果：

- 共有の`shared-sample`
- Alice個人の`personal-sample`
- Alice個人の`mcp-register-sample`

が表示される。

Bobの`bob-sample`は表示されない。

ユーザー名を特定できないエラーが出る場合は、次を確認します。

```bash
docker compose exec open-webui env | grep ENABLE_FORWARD_USER_INFO_HEADERS
docker compose logs --tail=200 knowledge-bridge
```

### 18.4 検索用カスタムモデル

検索Toolを付けたカスタムモデルを作成し、システム指示を設定します。

推奨する最小指示例：

```text
ナレッジ検索が必要な場合はsearch_knowledgeを使用してください。
ユーザーがプロジェクト名を指定した場合はprojectsへ指定してください。
プロジェクト名が不明な場合のみ、projectsを省略して横断検索してください。
検索結果だけで不足する場合に限りread_knowledge_sourceを使用してください。
原本を最初から読まないでください。
```

テスト会話：

```text
shared-sampleについて、Pythonの必要バージョンを教えてください。
```

期待結果：`projects=["shared-sample"]`で検索し、「Python 3.11以降」と回答する。

横断探索：

```text
サンプリング周期について書かれたプロジェクトを探してください。
```

期待結果：横断検索から`personal-sample`を特定する。

継続質問：

```text
そのプロジェクトの設定コードも確認してください。
```

期待結果：必要と判断した場合だけ`read_knowledge_source`を使い、`config.py`の該当部分を確認する。

### 18.5 登録専用カスタムモデル

`index_personal_knowledge`だけを付けた登録専用モデルを作成します。

推奨する最小指示例：

```text
このモデルは事前配置済みの個人ナレッジを登録する専用モデルです。
ユーザーが指定したプロジェクト名をindex_personal_knowledgeへ渡してください。
原本の作成、移動、上書き、削除は行いません。
登録中エラーの場合は「現在別の登録処理中です。しばらくしてから再度実行してください」と案内してください。
```

ホスト側で未登録プロジェクトを配置します。

```bash
mkdir -p knowledge/users/alice/webui-register-sample
cat > knowledge/users/alice/webui-register-sample/README.md <<'EOF_WEBUI_REG'
# WebUI Register Sample

登録確認コードはOPENWEBUI-MCP-2026です。
EOF_WEBUI_REG
```

会話：

```text
webui-register-sampleを登録してください。
```

期待結果：

- `private_alice_webui-register-sample`が作成される
- 原本は変更されない
- 登録完了が会話で報告される

検索用モデルで確認：

```text
webui-register-sampleから登録確認コードを検索してください。
```

期待結果：`OPENWEBUI-MCP-2026`が返る。

---

## 19. 異常系テスト

### 19.1 存在しないプロジェクト

```json
{
  "project": "not-found-project"
}
```

期待結果：配置済みプロジェクトが見つからない旨のエラー。

### 19.2 不正なパス指定

```json
{
  "project": "../bob/bob-sample"
}
```

期待結果：個人Knowledge領域直下のフォルダ名を指定するようエラー。

### 19.3 空の検索文

```json
{
  "query": ""
}
```

期待結果：検索文が空である旨のエラー。

### 19.4 存在しないプロジェクトを検索指定

```json
{
  "query": "テスト",
  "projects": ["not-found-project"]
}
```

期待結果：参照可能なプロジェクトが見つからない旨のエラー。

### 19.5 検索件数上限

```json
{
  "query": "プロジェクト",
  "limit": 1000
}
```

期待結果：`KB_SEARCH_MAX_LIMIT`の値、既定では10件以下に制限される。

### 19.6 原本読み取り行数上限

```json
{
  "source_ref": "kbsource://users/alice/personal-sample/src/config.py",
  "start_line": 1,
  "max_lines": 10000
}
```

期待結果：`KB_SOURCE_MAX_LINES`の値、既定では400行以下に制限される。

### 19.7 ユーザー情報なし

ヘッダーを付けないMCPクライアントから、`owner`も省略してToolを呼びます。

期待結果：ユーザー名を特定できない旨のエラー。

初期版ではユーザー情報は識別用であり、認証ではありません。外部公開は行わないでください。

---

## 20. 再登録テスト

Aliceの原本を修正します。

```bash
cat >> knowledge/users/alice/personal-sample/README.md <<'EOF_REINDEX'

再登録確認コードはREINDEX-2026です。
EOF_REINDEX
```

MCPまたはOpen WebUIから再登録します。

```json
{
  "project": "personal-sample"
}
```

期待結果：

- 既存Qdrant Collectionが削除・再構築される
- 原本は削除・移動されない
- `REINDEX-2026`が検索可能になる

```bash
uv run kb-search --owner alice \
  --project personal-sample \
  "REINDEX-2026"
```

Qdrant登録に失敗した場合は、原本を修正・削除せず、そのまま再登録を実行します。

---

## 21. 管理者CLI利用時の運用確認

`kb-index`は初期版以降、管理者・デバッグ用と位置付けます。

CLIを使う場合は、Open WebUIからの登録を停止してから実行します。初期版にはWeb登録のメンテナンス切替機能を実装していないため、次のいずれかで運用します。

- 登録専用カスタムモデルを一時的に非公開にする
- Open WebUIから登録Toolを一時的に外す
- `knowledge-bridge`を停止してホストCLIを実行する

最も確実な方法：

```bash
docker compose stop knowledge-bridge

uv run kb-index --shared knowledge/shared/shared-sample

# 完了後
docker compose start knowledge-bridge
```

検索用MCPも停止するため、利用者への周知が必要です。

CLIとWeb登録を同時に実行しないことを確認してください。

---

## 22. 合格判定

次をすべて満たした場合、初期版の結合テストを合格とします。

| No. | 確認項目 | 合格条件 |
|---:|---|---|
| 1 | TEI | Embeddingモデルが正常起動する |
| 2 | LiteLLM | `lab-embedding`でEmbeddingを生成できる |
| 3 | Qdrant | Collection作成・取得ができる |
| 4 | `kb-index` | 共有・個人Knowledgeを登録できる |
| 5 | `kb-search` | プロジェクト限定・横断検索ができる |
| 6 | ユーザー分離 | AliceからBobの個人Knowledgeが見えない |
| 7 | MCP接続 | 4つのToolを取得・実行できる |
| 8 | MCP登録 | 事前配置済み個人プロジェクトを登録できる |
| 9 | 同時実行 | 2件目が待機せずbusyエラーになる |
| 10 | 原本保護 | MCPコンテナから原本領域へ書き込めない |
| 11 | 原本参照 | 検索結果の`source_ref`から必要範囲を読める |
| 12 | 原本制限 | 他ユーザー・非対応形式・範囲外パスを拒否する |
| 13 | Open WebUI検索 | 会話から限定検索・横断検索ができる |
| 14 | Open WebUI登録 | 専用モデルから事前配置済みプロジェクトを登録できる |
| 15 | 再登録 | Qdrantを再構築し、原本は保持される |

---

## 23. 障害切り分け

### Embeddingに失敗する

```bash
docker compose logs --tail=200 tei
docker compose logs --tail=200 litellm
curl http://localhost:4000/v1/models \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY"
```

確認項目：

- TEIのモデルロード完了
- GPUメモリ不足
- LiteLLMの`api_base`
- `LITELLM_MASTER_KEY`
- `EMBEDDING_MODEL=lab-embedding`

### 登録できるが検索できない

確認項目：

- 登録時と検索時で同じEmbeddingモデルか
- Collection名が期待どおりか
- payloadに本文とmetadataがあるか
- `QDRANT_URL`が正しいか

```bash
curl -s http://localhost:6333/collections | jq .
uv run kb-search --owner alice --json "テスト"
```

### MCPへ接続できない

```bash
docker compose ps knowledge-bridge
docker compose logs --tail=200 knowledge-bridge
docker compose exec open-webui \
  sh -lc 'python - <<PY
import urllib.request
print(urllib.request.urlopen("http://knowledge-bridge:8000/mcp").status)
PY'
```

MCPエンドポイントは通常のWebページではないため、HTTPステータスだけでなくOpen WebUIまたはMCP InspectorでTool一覧を確認してください。

### Open WebUIでユーザーを特定できない

```bash
docker compose exec open-webui env \
  | grep ENABLE_FORWARD_USER_INFO_HEADERS
```

期待値：

```text
ENABLE_FORWARD_USER_INFO_HEADERS=true
```

また、Open WebUIの表示名ではなく、実際に転送されるユーザー名とKnowledgeディレクトリ名が一致しているか確認します。

### 原本参照に失敗する

検索結果の`source_ref`をそのまま利用してください。`logical_path`ではなく、原本参照用の`source_ref`を優先します。

```text
kbsource://shared/<実フォルダ名>/<相対パス>
kbsource://users/<owner>/<実フォルダ名>/<相対パス>
```

コンテナ内で存在確認：

```bash
docker compose exec knowledge-bridge \
  find /knowledge -type f | sort
```

---

## 24. テスト終了後

テスト用Collectionを削除する場合はQdrant側だけを削除します。原本ディレクトリは自動削除しません。

例：

```bash
for collection in \
  shared_shared-sample \
  private_alice_personal-sample \
  private_bob_bob-sample \
  private_alice_mcp-register-sample \
  private_alice_slow-register-sample \
  private_alice_webui-register-sample
do
  curl -X DELETE "http://localhost:6333/collections/${collection}"
done
```

原本を削除する場合は、テスト終了後に管理者が明示的に判断して削除してください。

```bash
rm -rf knowledge/shared/shared-sample
rm -rf knowledge/users/alice/personal-sample
rm -rf knowledge/users/alice/mcp-register-sample
rm -rf knowledge/users/alice/slow-register-sample
rm -rf knowledge/users/alice/webui-register-sample
rm -rf knowledge/users/bob/bob-sample
```

本番原本と混同しないよう、テスト専用Knowledgeルートを使用することを推奨します。

---

## 25. 初期版の既知の制約

- Open WebUIユーザー名とKnowledgeアカウント名が同一であることを前提とする
- ユーザー情報ヘッダーは認証ではなく識別情報として扱う
- 信頼できる内部ネットワークでのみ利用する
- MCP登録のロックはMCPサーバプロセス内だけである
- 管理者CLIとの競合は運用で防ぐ
- Qdrant Collectionは削除して再構築する
- 登録失敗時は原本を残し、再登録する
- 原本の配置・移動・上書き・削除は行わない
- チャット添付登録は次バージョン以降の検討事項
- PDF、DOCX、PPTXなどの原本参照は初期版では行わない
