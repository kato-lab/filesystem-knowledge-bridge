# filesystem-knowledge-bridge

整理・フリーズ済みのプロジェクトフォルダを、**階層構造と相対パスを保ったままQdrantへ登録**して、ナレッジとして扱う補助リポジトリです。

このプロジェクトは、プロジェクトフォルダをQdrantに登録するためのindexserのみの構成で、Knowledgeサーバを新しく作るものではありません。
他の部分は、次のような既存のOSSを組み合わせるdropcatとを想定しています。

- Chat UI: Open WebUI
- LLM / Embedding gateway: LiteLLM
- Vector DB: Qdrant
- 構造保持型インデックス作成: 本リポジトリ

## コンセプト

```text
生きたプロジェクト
  - 日々更新される
  - 未整理のメモや失敗コードを含む
  - Workspace Agentが直接参照する

        ↓ 整理・再現確認・freeze

Curated Knowledge Space
  - 共有または個人用として公開してよい
  - プロジェクトとしてフリーズしている
  - 引き継ぎ・再利用可能
  - フォルダ構造を維持する

        ↓ kb-index（非常駐）

Qdrant
  - project単位のcollection
  - nodeごとにrelative_path / logical_pathを保持

        ↓

Open WebUI / Agent
```

## このリポジトリが解決すること

- 別フォルダの同名ファイルを相対パスで区別する
- Markdownの見出し構造を維持して分割する
- ソースコードを構文単位で分割する
- PDF / DOCX / PPTXを形式別Readerで読み込む
- 全nodeへproject・owner・相対パスを付与する
- project単位でQdrant collectionを全置換する
- LiteLLM Proxy経由でEmbeddingを生成する

## 解決しないこと

- 生きたプロジェクトの常時監視
- 自動差分同期
- 独自Chat UI
- 独自ユーザ管理
- 独自RAG回答生成
- 原本ファイルの編集

## Quick start

### 1. 設定

```bash
cp .env.example .env
```

`.env`を環境に合わせて編集します。

### 2. Qdrantを起動

既存Qdrantを使う場合は不要です。

```bash
docker compose up -d qdrant
```

### 3. Python環境を作成

```bash
uv sync
```

### 4. dry-run

```bash
set -a
source .env
set +a

uv run kb-index examples/sample_project \
  --shared \
  --project-id sample-project \
  --dry-run
```

### 5. 登録

```bash
uv run kb-index examples/sample_project \
  --shared \
  --project-id sample-project
```

個人Knowledgeの場合:

```bash
uv run kb-index /mnt/ai-knowledge/users/alice/floor-map \
  --owner alice \
  --project-id floor-map
```

## Dockerでindexerを実行する

Python環境をホストへ入れたくない場合:

```bash
docker compose build indexer

docker compose run --rm indexer \
  /knowledge/shared/sample-project \
  --shared \
  --project-id sample-project
```

標準Composeでは `./examples` を `/knowledge` にread-onlyでマウントしています。indexerをホストのコマンドとして実行する場合には不要ですが、dockerから起動する場合は必要です。本番ではKnowledge専用領域を用意してbind元を変更してください。

また、ファイルサーバ上にNFSでknowledge領域を用意した場合は、knowledge領域全体を静的マウントしてbindします。例えば/mnt/ai-knowledgeにマウントした場合、docker のbind mountは次のようになります。

```yaml
volumes:
  - /mnt/ai-knowledge:/knowledge:ro
```

## Knowledge Spaceの構成例

```text
/mnt/ai-knowledge/
├── shared/          #共有ナレッジスペース
│   ├── manuals/
│   └── projects/
└── users/           #ユーザごとの個人ナレッジスペース
    ├── alice/       #ユーザaliceのナレッジスペース
    └── bob/         #ユーザbobのナレッジスペース
```

ホームディレクトリ(`/home`)全体をコンテナへbindする構成は推奨しません。読み取り専用でも、SSH鍵や通常作業ファイルまでコンテナから見えるのでセキュリティ上のリスクとなるためです。ナレッジスペースは別途専用領域を用意しましょう。その上で各ユーザナレッジスペースをautofsでマウントし、ホームディレクトリから ln -s /knowledge/users/alice /home/alice/knowledgeのようにシンボリックリンクを貼ると利便性もあがります。

## Metadata

各nodeには最低限、次のmetadataを付与します。

```json
{
  "scope": "shared",
  "owner": "shared",
  "project_id": "sample-project",
  "project_name": "sample_project",
  "relative_path": "src/main.py",
  "logical_path": "labknowledge://shared/sample-project/src/main.py",
  "file_name": "main.py",
  "file_extension": ".py",
  "chunk_index": 0
}
```

同名ファイルでも、`project_id + relative_path`で区別できます。

## Collection設計

本ツールでは**1 project = 1 collection**の構成を採用します。

```text
shared_sample-project
private_alice_floor-map
```

理由:

- project単位でOpen WebUIから選択しやすい
- 再登録時にcollection全置換できる
- 削除済みファイルや旧chunkが残らない
- metadata filterへ依存せず局所化しやすい

project数が非常に増えた場合は、将来1 collection + payload filter方式へ移行できます。

## Open WebUIとの役割分担

本ツールはQdrantへの登録までを担当します。
Open WebUI側では、外部Knowledge SourceやQdrant検索Toolを使ってcollectionを選択・検索します。OpenWebUIの標準ナレッジ機能とも共存でき、階層構造を必要としないナレッジについては、標準ナレッジ機能をつかったほうが使いやすいです。

- Curated Knowledge: 本リポジトリで登録
- Ad-hoc Knowledge: Open WebUI標準Knowledgeへ直接アップロード

## 原本への到達

本ツールでは原本はナレッジに登録せずチャンク化された情報のみをQdrantに登録しています。
原本への到達性を担保するため、metadataに原本の情報を埋め込んでいます。これはAIサーバ固有の絶対パスではなく、`logical_path`を保存します。

```text
labknowledge://shared/sample-project/src/main.py
```

これは、利用PC側で次のように対応付けます。

```text
Linux:   /knowledge/shared/sample-project/src/main.py
Windows: Z:\shared\sample-project\src\main.py
```

RAGで対象ファイルを探し、より詳しい解析が必要なら、Workspace Agentなどで原本を直接参照させることを想定しています。


## 登録したナレッジの使い方。
現在、登録したナレッジをAIから使う方法は、OpenWebUIの External Knowledge Source機能を使います。OpenWebUIのチャット以外（Agentなど）から使う場合は、OpenWebUIのAPIキー経由でカスタムモデルを参照して利用します。

将来的には小さなMCPサーバーを開発し、エージェントへのナレッジの提供や、プロジェクトが増えた時の登録やプロジェクト単位のフィルタリングなどを担当する予定です。



## Status
Experimental / MIT License
