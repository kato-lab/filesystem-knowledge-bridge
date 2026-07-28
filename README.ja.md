# filesystem-knowledge-bridge

フリーズ済みのプロジェクトフォルダをQdrantのCollectionとして登録し、Open WebUIのExternal Knowledge Sourcesから利用するための軽量インデクサです。

> システム全体を作り直さず、既存のRAGコンポーネントを活用し、プロジェクト登録部分だけを最適化します。

English documentation: [README.md](README.md)

## 概要

```text
フリーズ済みプロジェクト
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

独自の検索サーバは用意しません。Open WebUIがQdrantのCollectionを直接検索します。

## 特徴

- プロジェクト名・相対パスなどの構造情報を保持
- 原則として1プロジェクトを1つのQdrant Collectionへ登録
- 共有Knowledgeと個人Knowledgeに対応
- Markdown、ソースコード、テキスト、PDF、DOCX、PPTXに対応
- ファイル形式に応じたチャンク分割
- LiteLLMのOpenAI互換APIを通じてEmbeddingを生成
- Open WebUIが直接読める`text`・`metadata`をpayloadへ保存
- 再登録時は既存Collectionを削除して全置換
- ホスト側CLIと、必要に応じたコンテナ実行に対応

## 必要環境

- LinuxまたはmacOS
- Python 3.11以降
- [uv](https://docs.astral.sh/uv/)
- DockerおよびDocker Compose
- Open WebUI 0.10.2以降
- LiteLLM Proxy
- Qdrant
- TEI上の`BAAI/bge-m3`などのEmbeddingモデル

# 1. `kb-index`のインストール

## 1.1 ローカルユーザーへのインストール

```bash
uv tool install .
```

実行ファイルは通常、次へ配置されます。

```text
~/.local/bin/kb-index
```

`~/.local/bin`が`PATH`に含まれていることを確認してから、次を実行します。

```bash
kb-index --help
```

ソース修正後に再インストールする場合：

```bash
uv tool install --force .
```

開発中はインストールせずに実行することもできます。

```bash
uv run src/kb_index.py --shared examples
```

`pyproject.toml`にコマンドが登録済みなら、次でも実行できます。

```bash
uv run kb-index --shared examples
```

## 1.2 システム全体へのインストール

まず一般ユーザーでwheelを作成します。

```bash
rm -rf build dist src/*.egg-info
uv build
```

全ユーザーが使えるようにインストールします。

```bash
sudo mkdir -p /opt/uv-tools /usr/local/bin

sudo env \
  UV_TOOL_DIR=/opt/uv-tools \
  UV_TOOL_BIN_DIR=/usr/local/bin \
  uv tool install --force dist/*.whl
```

確認：

```bash
which kb-index
kb-index --help
```

想定される実行ファイル：

```text
/usr/local/bin/kb-index
```

アンインストール：

```bash
sudo env \
  UV_TOOL_DIR=/opt/uv-tools \
  UV_TOOL_BIN_DIR=/usr/local/bin \
  uv tool uninstall filesystem-knowledge-bridge
```

アンインストール時に指定するのは、実行コマンド名ではなく`pyproject.toml`のパッケージ名です。

# 2. CLIの設定

`kb-index`は次の環境変数を参照します。

```dotenv
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=

LITELLM_API_BASE=http://localhost:4000/v1
LITELLM_API_KEY=LiteLLMへ接続するキー
EMBEDDING_MODEL=lab-embedding

KNOWLEDGE_LOGICAL_ROOT=labknowledge://
```

LiteLLMを1つのMaster Keyで運用している場合：

```bash
export LITELLM_API_KEY="$LITELLM_MASTER_KEY"
```

ホスト側CLIからLiteLLMとQdrantへ到達できる必要があります。

## 基本的な使い方

```bash
kb-index --shared /path/to/project
kb-index /path/to/project
kb-index --owner alice /path/to/project
kb-index --project-id stable-project-id /path/to/project
kb-index --collection curated_project /path/to/project
kb-index --shared --dry-run /path/to/project
```

既定のCollection名：

```text
shared_<project-id>
private_<owner>_<project-id>
```

# 3. システム全体の構築

最小の常駐構成は、Open WebUI、LiteLLM、Qdrant、BGE-M3を動かすTEIの4サービスです。インデクサは常駐させる必要はありません。

## 3.1 `.env`

```dotenv
COMPOSE_PROJECT_NAME=lab-ai

OPENWEBUI_PORT=3000
WEBUI_SECRET_KEY=十分に長いランダム文字列へ変更
ENABLE_SIGNUP=true
RAG_TOP_K=5

LITELLM_PORT=4000
LITELLM_MASTER_KEY=十分に強いキーへ変更

OPENAI_API_KEY=
GEMINI_API_KEY=
ANTHROPIC_API_KEY=

EMBEDDING_MODEL=lab-embedding

QDRANT_HTTP_PORT=6333
QDRANT_API_KEY=

KNOWLEDGE_LOGICAL_ROOT=labknowledge://
```

`.env`はGitへ登録しません。

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

利用者へ公開する必要があるのはOpen WebUIだけです。上の例では、ホスト側の`kb-index`から利用するため、LiteLLMとQdrantをlocalhostにだけ公開しています。TEIはホストへ公開していません。

## 3.3 LiteLLMの`config.yaml`

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

通常のチャットモデルも、必要に応じて同じ`model_list`へ追加します。

## 3.4 起動と確認

```bash
docker compose up -d
docker compose ps
```

LiteLLMのモデル一覧：

```bash
curl http://localhost:4000/v1/models \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY"
```

Embedding確認：

```bash
curl http://localhost:4000/v1/embeddings \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "lab-embedding",
    "input": "テスト用の文章",
    "encoding_format": "float"
  }'
```

Qdrant確認：

```bash
curl http://localhost:6333/collections
```

# 4. プロジェクトの登録

```bash
export QDRANT_URL=http://localhost:6333
export LITELLM_API_BASE=http://localhost:4000/v1
export LITELLM_API_KEY="$LITELLM_MASTER_KEY"
export EMBEDDING_MODEL=lab-embedding

kb-index --shared examples
```

このコマンドは、対応ファイルの探索、パース・チャンク分割、LiteLLM経由のEmbedding生成、Collectionの再作成、Open WebUI向けpayloadの保存を行います。

登録内容を1件確認：

```bash
curl http://localhost:6333/collections/shared_examples/points/scroll \
  -H "Content-Type: application/json" \
  -d '{
    "limit": 1,
    "with_payload": true,
    "with_vector": false
  }'
```

payloadには次のような項目が含まれます。

```json
{
  "text": "チャンク本文",
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

# 5. Open WebUIのExternal Knowledge Sourcesから利用する

## 5.1 Embedding設定を確認する

```text
管理者パネル
→ 設定
→ ドキュメント
→ 埋め込み
```

設定例：

```text
埋め込みモデルエンジン: OpenAI
API Base URL: http://litellm:4000/v1
埋め込みモデル: lab-embedding
```

Open WebUIが検索クエリに使うEmbeddingモデルは、`kb-index`が登録時に使ったモデルと一致させる必要があります。

## 5.2 External Knowledge Sourceを追加する

```text
管理者パネル
→ 設定
→ 連携
→ External Knowledge Sources
→ Add Knowledge Connection
```

設定例：

```text
名前: Curated Knowledge
Provider: Qdrant
Endpoint: http://qdrant:6333
API Key / Token: Qdrant認証を使わない場合は空欄

コレクション: shared_examples
Content Field: payload.text
Vector Field: デフォルト
Metadata Field: payload.metadata
Document ID Field: id
```

Test Queryへ次のような質問を入力します。

```text
Pythonの必要バージョンは何ですか？
```

`Test Succeeded`と表示されることを確認してから接続を作成します。

## 5.3 チャットで利用する

作成したKnowledge Connectionをモデルまたはチャットへ付け、次のような質問をします。

```text
Pythonの必要バージョンは何ですか？
main.pyは何をするプログラムですか？
```

正常に動作していれば、登録したプロジェクトの内容に基づく回答とSource表示を確認できます。

# 対応ファイル形式

- Markdown：`.md`、`.markdown`
- テキスト・構造化テキスト：`.txt`、`.rst`、`.yaml`、`.yml`、`.json`、`.csv`、`.toml`、`.ini`、`.cfg`、`.tex`
- ソースコード：Python、JavaScript、TypeScript、Java、C/C++、C#、Go、Rust、Ruby、PHP
- 文書：PDF、DOCX、PPTX

# 設計方針

- 既存コンポーネントを可能な限りそのまま利用する
- 必要になるまで独自検索サーバを作らない
- 登録処理と検索処理を分離する
- プロジェクト構造と原本情報をmetadataとして保持する
- 差分更新を先回りして実装せず、当面は全置換で運用する
- MCPや登録Toolを追加する前に、現在動作しているIndexerを安定させる

# ライセンス

MIT

# MCPサービス（v0.2.0）

v0.2.0では、同じコードとDockerイメージから二つのMCPサービスを起動します。

```text
knowledge-read-mcp       検索・一覧・原本参照
knowledge-register-mcp   incoming取込・Qdrant登録
```

## 読み取りMCP

接続先：`http://<host>:8000/mcp`

- `search_knowledge`
- `list_knowledge_projects`
- `read_knowledge_source`

原本領域は読み取り専用でマウントします。

## 登録MCP

接続先：`http://<host>:8001/mcp`

- `list_incoming`
- `register_incoming_project`
- `reindex_stored_project`

一般ユーザーは、あらかじめ次の場所へ展開済みプロジェクトを置きます。

```text
/incoming/users/<owner>/<project>/
```

`register_incoming_project` はincomingを削除せず、次へコピーしてから登録します。

```text
/knowledge/users/<owner>/<project>/
```

同名の保存済み原本がある場合は自動上書きせず、エラーを返します。Qdrant登録に失敗した場合は、保存済み原本を使って `reindex_stored_project` を再実行できます。

## 起動

```bash
docker compose -f docker-compose.yml.example up -d --build \
  knowledge-read-mcp knowledge-register-mcp
```

ownerは初期版では次のHTTPヘッダーから取得します。

```text
X-Knowledge-Owner
X-OpenWebUI-User-Name
```

これは完全な認証機構ではありません。信頼できる内部ネットワークでのみ利用してください。
