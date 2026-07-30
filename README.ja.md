# filesystem-knowledge-bridge

**filesystem-knowledge-bridge** は、フリーズ済みのプロジェクトフォルダを **Qdrant Collection** として登録し、CLI や MCP から検索・閲覧できる軽量なナレッジ管理・検索ツールです。

> **フリーズ済みプロジェクト**とは、開発や編集が一段落し、特定バージョンとして内容を固定したプロジェクトを指します。本ツールでは、このようなプロジェクトをナレッジとして登録・管理することを想定しています。

ソースコード、Markdown、PDF、Office文書などをインデックス化し、プロジェクト単位でナレッジを管理します。検索結果から必要に応じて原本ファイルを参照できるため、AIエージェントやチャットシステムの知識基盤として利用できます。

本プロジェクトはナレッジの登録・検索・閲覧に特化しており、Open WebUIなど特定のUIには依存しません。

## 主な機能

- 1プロジェクトを1つのQdrant Collectionとして登録
- 共有ナレッジと個人ナレッジを分離
- `kb-index`による管理者向け登録
- `kb-search`によるCLI検索
- 読み取りMCPによる検索・一覧・原本参照
- 登録MCPによるincomingフォルダからの登録・再登録
- 原本ファイルをQdrantへ格納せず、ファイルシステム上に保持

## 構成

```text
管理者CLI
├── kb-index
└── kb-search

AIクライアント
├── Read MCP
│   ├── search_knowledge
│   ├── list_knowledge_projects
│   └── read_knowledge_source
└── Register MCP
    ├── list_incoming
    ├── register_incoming_project
    └── reindex_stored_project

                    ┌──────────┐
                    │ Qdrant   │
                    └──────────┘
                         ▲
                         │
              filesystem-knowledge-bridge
                         │
       ┌─────────────────┴─────────────────┐
       │                                   │
/knowledge 原本領域                 /incoming 登録候補
```

読み取りMCPと登録MCPは、同じPythonパッケージとDockerイメージを共有し、別サービスとして起動します。

## Collection名

```text
共有: shared_<project-id>
個人: private_<owner>_<project-id>
```

各ユーザーは、共有ナレッジと本人の個人ナレッジを検索する運用を想定しています。初期版ではownerの本人確認や認証は実装していないため、MCPはlocalhostまたは信頼できる内部ネットワークだけに公開してください。

## 対応ファイル

- Markdown: `.md`, `.markdown`
- テキスト・設定: `.txt`, `.rst`, `.yaml`, `.yml`, `.json`, `.csv`, `.toml`, `.ini`, `.cfg`, `.tex`
- ソースコード: Python、JavaScript、TypeScript、Java、C/C++、C#、Go、Rust、Ruby、PHP
- 文書: PDF、DOCX、PPTX

## インストール

### 開発環境・ホストCLI

リポジトリを取得した後、プロジェクト環境を同期します。

```bash
uv sync
```

CLIは`uv run`経由で実行します。

```bash
uv run kb-index --help
uv run kb-search --help
```

依存ライブラリを追加する場合は、`pyproject.toml`を直接編集せず`uv add`を使用します。

```bash
uv add <package-name>
```

## 環境変数

```dotenv
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
LITELLM_API_BASE=http://localhost:4000/v1
LITELLM_API_KEY=
EMBEDDING_MODEL=lab-embedding
KNOWLEDGE_LOGICAL_ROOT=labknowledge://
```

登録時と検索時には同じEmbeddingモデルを使用してください。

## CLIで登録

共有ナレッジ:

```bash
kb-index --shared /path/to/project
```

個人ナレッジ:

```bash
kb-index --owner alice /path/to/project
```

再登録時は既存Collectionを削除して再構築します。原本ファイルは変更・削除しません。

## CLIで検索

共有ナレッジのみ:

```bash
kb-search "MCPサーバの構成"
```

共有＋個人ナレッジ:

```bash
kb-search --owner alice "MCPサーバの構成"
```

プロジェクト限定:

```bash
kb-search --owner alice \
  --project filesystem-knowledge-bridge \
  "登録方法"
```

## Docker Compose

`.env.example`を`.env`へコピーし、Knowledge領域を設定します。

```dotenv
KNOWLEDGE_HOST_ROOT=/mnt/knowledge
KNOWLEDGE_INCOMING_HOST_ROOT=/mnt/knowledge-incoming
```

MCPサービスだけをビルド・起動する場合:

```bash
docker compose -f docker-compose.yml.example up -d --build \
  knowledge-read-mcp knowledge-register-mcp
```

接続先:

```text
Read MCP:     http://localhost:8000/mcp
Register MCP: http://localhost:8001/mcp
```

## Read MCP

### `search_knowledge`

共有ナレッジと、owner指定時はその個人ナレッジを検索します。

```json
{
  "query": "Qdrantの設定",
  "owner": "alice",
  "projects": ["filesystem-knowledge-bridge"],
  "limit": 5
}
```

`projects`を省略すると、参照可能なCollectionを横断検索し、全体上位だけを返します。

### `list_knowledge_projects`

参照可能なプロジェクトを一覧表示します。

### `read_knowledge_source`

検索チャンクだけでは前後関係が不足する場合に、テキスト形式の原本を行範囲付きで参照します。通常検索で自動的に原本全文を返すことはありません。

## Register MCP

登録候補は、SMBなどで次へ事前配置します。

```text
/incoming/users/<owner>/<project>/
```

### `list_incoming`

ownerのincomingにある登録候補を一覧表示します。

### `register_incoming_project`

incomingのプロジェクトを次へコピーし、個人Knowledgeとして登録します。

```text
/knowledge/users/<owner>/<project>/
```

- incoming原本を削除・移動しません
- 保存済み同名原本を自動上書きしません
- 同名原本がある場合はエラーを返します
- 登録処理は同時に1件だけ実行します
- Qdrant登録失敗後も保存済み原本は残ります

### `reindex_stored_project`

保存済み原本からQdrant Collectionを削除・再構築します。原本は変更しません。

## 原本領域

```text
/knowledge/
├── shared/<project>/
└── users/<owner>/<project>/

/incoming/
└── users/<owner>/<project>/
```

読み取りMCPでは`/knowledge`を読み取り専用でマウントします。登録MCPだけが保存先`/knowledge`への書き込み権限を持ち、`/incoming`は読み取り専用で参照します。

## MCPテスト

詳しい手順は[MCP_TEST.ja.md](MCP_TEST.ja.md)を参照してください。

## ライセンス

MIT License


### Open WebUIなど別コンテナから接続する場合

MCPのHTTP transportはHostヘッダーを検証します。Dockerサービス名を変更した場合は、`.env` の許可ホストも合わせて変更してください。

```dotenv
KNOWLEDGE_READ_MCP_ALLOWED_HOSTS=knowledge-read-mcp:8000,localhost:8000,127.0.0.1:8000
KNOWLEDGE_REGISTER_MCP_ALLOWED_HOSTS=knowledge-register-mcp:8001,localhost:8001,127.0.0.1:8001
```

設定値はComposeから各コンテナの `MCP_ALLOWED_HOSTS` へ渡されます。サービス名はPythonソースには固定していません。

## Open WebUIからZIPをアップロードして登録する

v0.3.0では、ZIPを`incoming`へ配置するだけの`knowledge-upload-api`を追加しています。
Uploaderは登録やインデックス作成を行いません。Open WebUIの登録専用モデルが、次の2つのToolを順に呼び出します。

```text
添付ZIPあり:
  Knowledge Project Uploader.upload_project
    → Knowledge Register.register_incoming_project

添付ZIPなし:
  Knowledge Register.register_incoming_project
```

Open WebUI用Workspace Toolの例は`openwebui/knowledge_uploader_tool.py`、設定・試験手順は`UPLOAD_TEST.ja.md`を参照してください。
