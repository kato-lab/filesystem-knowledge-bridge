# v0.2.0 実装案

## 初期版の範囲

- `kb-index`：既存CLIを維持し、登録本体を `index_directory()` として共通化
- `kb-search`：共有Collectionと指定ownerの個人Collectionを横断検索
- `kb-mcp`：Streamable HTTPで次のToolを公開
  - `search_knowledge`
  - `list_knowledge_projects`
  - `read_knowledge_source`
  - `index_personal_knowledge`
- 一般ユーザー登録は、事前配置済みの `/knowledge/users/<owner>/<project>/` のみ
- MCPコンテナから原本領域はread-only
- 登録は同時1件。競合時は待たずにbusyエラー
- 原本の作成・移動・上書き・削除は一切行わない
- Qdrant Collectionは従来どおり削除して再構築

## 今回実装しないもの

- チャット添付ZIPの受け取り
- アップロードAPI
- ZIP展開・検証
- 原本の配置・世代管理・バックアップ
- ジョブキューと自動再試行
- 認証済みユーザーとownerの厳密なマッピング

## ユーザー識別

Open WebUIで `ENABLE_FORWARD_USER_INFO_HEADERS=true` を有効にすると、
`X-OpenWebUI-User-Name` をowner候補として利用する。

外部エージェントはMCP接続時に `X-Knowledge-Owner` ヘッダーを設定できる。
Tool引数の `owner` も初期版のフォールバックとして残している。

これらは識別情報であって認証ではない。初期版は信頼できる内部ネットワークでの利用を前提とする。
セキュアな外部公開は対象外とし、必要になった時点で署名付きヘッダーまたは認証連携を別途設計する。

## 検索

`projects` 指定時は指定Collectionのみを検索し、省略時は共有Collectionと本人の個人Collectionを横断する。
各Collectionから候補を取得した後、全体スコア順に並べ、最終上位件数だけを返す。

## 原本参照

検索結果には次の2種類の参照情報を返す。

- `logical_path`：安定した論理識別子
- `source_ref`：実際の原本ディレクトリ名を保持した原本参照用URI

原本参照は `source_ref` を用い、テキスト・ソースコード系の形式だけに限定する。
既定200行、最大400行で、全文を自動的に返さない。

## Open WebUI接続先

```text
http://knowledge-bridge:8000/mcp
```

Open WebUI側ではユーザー情報ヘッダー転送を有効にする。

```yaml
ENABLE_FORWARD_USER_INFO_HEADERS: "true"
```

## 原本配置例

```text
/knowledge/
├── shared/
│   └── shared-project/
└── users/
    └── alice/
        └── personal-project/
```

一般ユーザーは自分の領域へフリーズ済みプロジェクトを事前配置し、登録専用モデルで次のように指示する。

```text
personal-projectを登録して
```

Toolは原本を変更せず、Qdrant Collectionのみを再構築する。
