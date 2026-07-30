# Upload API / Open WebUI Uploader Tool テスト

## 1. Upload APIを起動する

```bash
sudo docker compose -f docker-compose.yml.example up -d --build knowledge-upload-api
```

確認します。

```bash
curl -fsS http://localhost:8002/health
```

期待結果:

```json
{"status":"ok"}
```

## 2. HTTP API単体テスト

登録候補ZIPを作成します。

```bash
cd examples
zip -r ../sample-project-upload.zip sample_project
cd ..
```

アップロードします。

```bash
curl -fsS -X POST http://localhost:8002/uploads/projects \
  -F owner=tkato \
  -F project=sample-project-upload \
  -F archive=@sample-project-upload.zip
```

期待結果:

```json
{
  "status": "uploaded",
  "source_preserved": true,
  "owner": "tkato",
  "project": "sample-project-upload",
  "incoming_path": "/incoming/users/tkato/sample-project-upload"
}
```

ホスト側でも確認します。

```bash
test -d /mnt/knowledge-incoming/users/tkato/sample-project-upload
```

同じprojectへ再アップロードすると、上書きせず `409 Conflict` になることを確認します。

## 3. Open WebUIへUploader Toolを登録する

1. Open WebUIへ管理者でログインします。
2. `Workspace` → `Tools` → `Create Tool` を開きます。
3. IDを `knowledge_project_uploader` とします。
4. `openwebui/knowledge_uploader_tool.py` の内容を貼り付けて保存します。
5. ToolのValvesを開き、次を確認します。

```text
upload_api_url = http://knowledge-upload-api:8002
uploads_root   = /app/backend/data/uploads
```

Open WebUIのWorkspace Toolは、チャット添付のメタデータを`__files__`、ログインユーザー情報を`__user__`として受け取ります。ファイル本体はOpen WebUIコンテナ内のuploadsディレクトリから読み出します。

## 4. 登録専用モデルへToolを割り当てる

登録専用モデルに次を割り当てます。

- Workspace Tool: `Knowledge Project Uploader`
- MCP Server: `Knowledge Register`

システムプロンプト例:

```text
あなたはfilesystem-knowledge-bridgeの登録専用アシスタントです。

プロジェクト登録の依頼を受けたら、次の規則に従ってください。

1. 添付ZIPがある場合
   - upload_projectを呼び出してincomingへ配置する。
   - アップロード成功後、返されたownerとprojectを使って
     register_incoming_projectを呼び出す。

2. 添付ファイルがない場合
   - 指定されたprojectがincomingにあるものとして
     register_incoming_projectを呼び出す。

3. project名が省略され、ZIPが添付されている場合
   - ZIPのファイル名からproject名を推定してupload_projectを呼び出す。

4. アップロードに失敗した場合
   - register_incoming_projectは呼び出さない。

5. アップロード成功後に登録が失敗した場合
   - incomingにはファイルが残っていることを説明し、
     再アップロードではなく登録の再実行を案内する。

通常の検索や一般質問には回答せず、検索用モデルの利用を案内してください。
```

## 5. Open WebUIからのテスト

### 添付あり

ZIPを1個添付して、次のように入力します。

```text
sample-project-webuiとして登録してください
```

期待するTool呼び出し順:

```text
upload_project
  ↓
register_incoming_project
```

### 添付あり・project名省略

```text
このプロジェクトを登録してください
```

期待:

- ZIP名からproject名を推定する
- `upload_project` → `register_incoming_project` の順に実行する

### 添付なし

incomingへ事前配置した状態で、次を入力します。

```text
sample-project-incomingを登録してください
```

期待:

- Uploader Toolを呼ばない
- `register_incoming_project`だけを呼ぶ

## 6. 仕様上の注意

- UploaderはZIPの受け取りとincomingへの展開だけを担当します。
- UploaderはQdrant、Embedding、knowledge領域を操作しません。
- incomingの同名projectは自動上書きしません。
- ZIP Slipとなるパス、シンボリックリンク、サイズ・ファイル数上限超過は拒否します。
- Open WebUIのユーザーemailの`@`より前をownerとして使用します。

## 日本語project名の確認

```bash
curl -i -X POST http://localhost:8002/uploads/projects \
  -F owner=tkato \
  -F 'project=引き継ぎ資料_2025年度_末永栞奈' \
  -F archive=@handover.zip
```

期待結果:

- incomingフォルダ名が`引き継ぎ資料_2025年度_末永栞奈`のまま保持される
- Uploaderは`project_id`を生成しない
- 続くRegister MCP呼び出しでUUIDの`project_id`が生成される
