# v0.3.0 最小API実装案

## v0.2.0からの変更範囲

v0.2.0のMCP・検索・事前配置済み登録の実装を維持し、ZIP登録用の汎用HTTP APIだけを追加する。
専用Web UI、Open WebUI固有のファイル処理、incomingフォルダ、世代管理DBは追加しない。

## 提供インターフェース

- MCP: `http://knowledge-bridge:8000/mcp`
- ZIP登録API: `POST /api/projects/upload`

## ZIP登録API

`multipart/form-data`で次を送る。

- `file`: ZIPファイル
- `project`: 保存先プロジェクト名
- `project_id`: 任意。省略時はprojectから生成

ownerは既存MCPと同じく、次のヘッダーから取得する。

1. `X-Knowledge-Owner`
2. `X-OpenWebUI-User-Name`

これは認証ではなく、信頼できる内部ネットワークでのユーザー識別を前提とする。

### curl例

```bash
curl -X POST http://knowledge-bridge:8000/api/projects/upload \
  -H "X-Knowledge-Owner: alice" \
  -F "project=project-a" \
  -F "file=@project-a.zip"
```

## 原本の扱い

アップロードZIPは次へ保存する。

```text
/knowledge/uploads/users/<owner>/<uuid>_<filename>.zip
```

展開済み原本は次へ配置する。

```text
/knowledge/users/<owner>/<project>/
```

本バージョンでは、同名の原本がすでに存在する場合はHTTP 409を返す。
既存原本の上書き、移動、退避、削除は行わない。
Qdrant Collectionの再構築は、原本配置に成功した後で既存の`index_directory()`を呼んで行う。

登録に失敗しても、保存済みZIPと配置済み原本は自動削除しない。
一時展開ディレクトリだけは失敗時に削除する。

## 同時登録

MCPの事前配置済み登録とHTTPアップロード登録は、同じ非待機ロックを共有する。
別の登録処理が動作中の場合は、待ち行列へ入れずHTTP 409またはMCP Toolエラーを返す。

## ZIP検証

- ZIP形式のみ
- 絶対パスと`..`を拒否
- シンボリックリンクを拒否
- アップロードサイズ上限
- 展開後サイズ上限
- ファイル数上限

## 今回実装しないもの

- 専用登録画面
- Open WebUI専用Tool
- incomingフォルダ
- 既存原本の自動退避・上書き
- 原本削除API
- ジョブキュー
- 認証・ownerマッピング

## Compose上の権限

アップロードAPIが原本とZIPを保存するため、knowledge-bridgeだけが`/knowledge`をRWマウントする。
Open WebUIや他のコンテナへ原本領域を直接マウントする必要はない。

ホストから動作確認する場合は、Composeで`127.0.0.1:8000:8000`を一時的に公開する。
