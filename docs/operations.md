# Operations

## 共有Knowledgeを登録

```bash
kb-index /mnt/ai-knowledge/shared/projects/floor-map \
  --shared \
  --project-id floor-map
```

## 個人Knowledgeを登録

```bash
kb-index /mnt/ai-knowledge/users/alice/floor-map \
  --owner alice \
  --project-id floor-map
```

## 再登録

同じprojectを再登録すると、既存collectionを削除して全再作成します。
差分更新・manifest DB・file watcherは持ちません。

## 推奨運用

1. 生きたprojectは通常のWorkspaceで管理
2. Agentで整理・再現確認
3. Knowledge Spaceへfreeze
4. `kb-index`を実行
5. Open WebUIでcollectionを登録・選択
