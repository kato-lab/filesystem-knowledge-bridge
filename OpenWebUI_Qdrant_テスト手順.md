# OpenWebUI + LiteLLM + Qdrant ナレッジ基盤 テスト手順

## 構成

``` text
TEI(BGE-M3)
      │
      ▼
LiteLLM
      │
      ├── kb-index
      └── OpenWebUI
             │
             ▼
          Qdrant
             │
             ▼
External Knowledge Sources
```

## Step 0 コンテナ確認

``` bash
docker compose ps
```

期待:

    open-webui Up
    litellm Up
    qdrant Up
    tei Up

## Step 1 TEI

``` bash
curl http://localhost:8081/health
curl http://localhost:8081/info
```

```bash
> curl http://localhost:8081/health
> curl http://localhost:8081/info
{"model_id":"BAAI/bge-m3","model_sha":null,"model_dtype":"float16","model_type":{"embedding":{"pooling":"cls"}},"max_concurrent_requests":512,"max_input_length":4096,"max_batch_tokens":4096,"max_batch_requests":null,"max_client_batch_size":16,"auto_truncate":true,"tokenization_workers":32,"version":"1.8.3","sha":"78502d8e61223d2c73d4bb7aeaea46787e90d596","docker_label":"sha-78502d8"}%             
>
```
healthがOK、モデルがBAAI/bge-m3であることを確認。

## Step 2 LiteLLM

``` bash
curl http://localhost:4000/health
curl http://localhost:4000/v1/models
```

`lab-chat`と`lab-embedding`が表示されること。

Embedding確認:

``` bash
curl http://localhost:4000/v1/embeddings -H "Authorization: Bearer lab-ai-master-key" -H "Content-Type: application/json" -d '{"model":"lab-embedding","input":"京都橘大学"}'
```

embedding配列が返ればOK。

## Step 3 Qdrant

Dashboard:

http://localhost:6333/dashboard

Collection一覧が表示されること。

## Step 4 kb-index

hello.txtを含むexamplesを用意し

``` bash
kb-index examples --shared
```

Collection作成・Embedding・登録件数が表示されること。

## Step 5 Qdrant確認

Dashboard→Collection→Pointsでpayload(content, metadata, owner,
scope等)を確認。

## Step 6 API確認

``` bash
curl http://localhost:6333/collections
```

Collectionが見えること。

## Step 7 OpenWebUI

`lab-chat`で「こんにちは」が正常応答すること。

## Step 8 External Knowledge Sources

Admin → Integrations → External Knowledge Sources

Provider=Qdrant Endpoint=http://qdrant:6333
Collection=作成したCollection

## Step 9 Test Query

「テスト」でhello.txtがヒットすること。

## Step 10 チャット

Knowledgeを追加し「これは何のファイル？」と質問。

「これはテストです。」を根拠に回答すること。

## Step 11 Source

hello.txt等のSourceが表示されること。

## トラブルシューティング

  止まる場所   確認
  ------------ ---------------------
  Step2        LiteLLM
  Step4        kb-index
  Step5        Qdrant登録
  Step8        External Knowledge
  Step10       Embeddingモデル一致

## 最重要確認

``` bash
curl http://localhost:4000/v1/models
```

`lab-embedding`が表示され、OpenWebUIとkb-indexが同じEmbeddingモデルを利用していることを確認する。
