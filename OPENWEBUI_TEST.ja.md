# Open WebUI 連携試験

## 目的

filesystem-knowledge-bridge の Read MCP / Register MCP を Open WebUI
へ登録し、 チャットから検索・閲覧・登録が利用できることを確認します。

前提: `MCP_TEST.ja.md` が完了していること。

------------------------------------------------------------------------

# 1. Read MCP を登録する

1.  管理者で Open WebUI にログイン
2.  **管理(Admin)** → **Tools** → **MCP Servers**
3.  **Add MCP Server** をクリック
4.  次のように入力

  項目      値
  --------- --------------------------------------
  Name      Knowledge Read
  URL       `http://knowledge-read-mcp:8000/mcp`
  Enabled   ON

5.  Save を押す
6.  Status が Connected になることを確認

## 2. Register MCP を登録する

同様に追加します。

  項目      値
  --------- ------------------------------------------
  Name      Knowledge Register
  URL       `http://knowledge-register-mcp:8001/mcp`
  Enabled   ON

Connected になることを確認します。

------------------------------------------------------------------------

# 3. Tool を確認する

Knowledge Read

-   search_knowledge
-   list_knowledge_projects
-   read_knowledge_source

Knowledge Register

-   list_incoming
-   register_incoming_project
-   reindex_stored_project

------------------------------------------------------------------------

# 4. Read MCP の試験

## Project 一覧

    利用可能な Knowledge Project を一覧表示してください

期待

-   list_knowledge_projects が呼ばれる
-   examples, sample-project が表示される

## 検索

    sample-project の概要を教えてください

期待

-   search_knowledge が呼ばれる

## 原本参照

    src/main.py を読んでください

期待

-   read_knowledge_source が呼ばれる

------------------------------------------------------------------------

# 5. Register MCP の試験

事前に

    incoming/users/tkato/sample-project2

を配置します。

    登録候補を一覧表示してください

↓

list_incoming

    sample-project2 を登録してください

↓

register_incoming_project

    sample-project2 を再インデックスしてください

↓

reindex_stored_project

------------------------------------------------------------------------

# 6. 自然言語試験

    Python のサンプルプロジェクトを探し、
    README と main.py を確認して概要を説明してください。

期待

-   search
-   read

を自動利用して回答する。

------------------------------------------------------------------------

# チェックリスト

-   [ ] Read MCP 接続
-   [ ] Register MCP 接続
-   [ ] Tool 一覧
-   [ ] Project 一覧
-   [ ] 検索
-   [ ] 原本参照
-   [ ] 登録
-   [ ] 再インデックス
-   [ ] Tool 自動利用
