# Design decisions

## なぜQdrant Loaderではなく小さな自作indexerか

Qdrant Loaderは多形式変換、変更検知、MCP検索など多くの機能を持つ優れたOSSです。
一方、本構成では次の3点を最優先します。

1. `project_id + relative_path`による厳密な同名ファイル識別
2. Markdown / code / PDF / DOCX / PPTXごとの分割方針を明示的に制御
3. `logical_path`を含むmetadata schemaを研究室規約として固定

Knowledgeはfreeze後に低頻度で登録するため、差分同期や常時監視を削り、project単位全置換で実装を小さくします。
