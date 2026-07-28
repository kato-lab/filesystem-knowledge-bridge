# v0.2.0 実装方針

v0.1.0のIndexerを起点に、同じPythonパッケージとDockerイメージから二つのMCPサービスを起動します。

- `knowledge-read-mcp`: 検索・一覧・慎重な原本参照。原本領域は読み取り専用。
- `knowledge-register-mcp`: incomingに事前配置された個人projectの登録・再登録。

登録MCPはファイルアップロードを受け付けません。原本はSMBなどで`incoming/users/<owner>/<project>/`へ配置します。登録時はincomingをコピーし、incoming原本を削除・移動しません。保存済み同名原本がある場合も自動上書きせずエラーにします。

認証・ownerの本人確認は初期版では実装していません。MCPポートはlocalhostまたは信頼できる内部ネットワークだけに公開してください。


## uvによる依存管理

依存管理は`uv`のプロジェクト管理機能へ統一します。

- 開発環境の構築: `uv sync`
- 依存の追加: `uv add <package-name>`
- CLIの実行: `uv run <command>`
- Dockerイメージ内の環境構築: `uv sync --no-dev`

`uv pip`や`pip install`は使用しません。`uv.lock`を生成・更新できる環境では、Dockerfileの同期コマンドを`uv sync --frozen --no-dev`へ変更できます。
