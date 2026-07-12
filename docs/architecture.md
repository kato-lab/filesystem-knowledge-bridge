# Architecture

## Active workspace and curated Knowledge

```text
Active project
  ↓ Workspace Agent
整理・再現確認
  ↓ freeze
Knowledge Space
  ↓ kb-index
Qdrant
  ↓ Open WebUI / search Tool
```

## 自作部分

常駐しません。

```text
kb-index
  - scan
  - format-specific read
  - structure-aware split
  - metadata normalization
  - embedding via LiteLLM
  - replace Qdrant collection
  - exit
```

## 既存OSSへ任せる部分

- Open WebUI: 認証・Chat UI・Ad-hoc Knowledge
- LiteLLM: LLM / Embedding gateway
- Qdrant: Vector storage
- LlamaIndex: Reader / Node Parser / VectorStore integration
