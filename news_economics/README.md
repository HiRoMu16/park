# 最新の経済ニュース（5件）

RSS フィードから最新の経済/ビジネス系ニュースを取得し、直近 5 件だけを表示するミニ Web アプリです。

## 使い方（ローカル実行）

- 前提: Node.js 16+ がインストール済み
- 手順:
  1. 依存関係をインストール
     ```bash
     npm install
     ```
  2. 開発サーバーを起動
     ```bash
     npm start
     ```
  3. ブラウザで `http://localhost:3000` を開く

バックエンドが Yahoo!ニュース（経済）および Reuters の RSS を取得・集約し、`/api/news` で最新 5 件を JSON 返却します。フロントエンドは同 API を叩いて表示します。

## フィードの変更（任意）

`server.js` の `FEEDS` を編集すると、対象の RSS を増減できます。経済分野の RSS を複数指定しておくと、5 件に満たない場合の補完になります。

```js
const FEEDS = [
  { url: 'https://news.yahoo.co.jp/rss/categories/business.xml', label: 'Yahoo!ニュース 経済' },
  { url: 'https://feeds.reuters.com/reuters/businessNews', label: 'Reuters Business' }
];
```

## API エンドポイント

- `GET /api/news`
  - レスポンス例:
    ```json
    {
      "updatedAt": "2025-01-01T00:00:00.000Z",
      "count": 5,
      "items": [
        { "title": "...", "link": "...", "source": "...", "isoDate": "..." }
      ]
    }
    ```
  - クエリ `?q=円高,インフレ` でタイトルのキーワード部分一致フィルタが可能（任意）。

## 補足

- 取得元の RSS 仕様変更や一時的な接続不良で表示件数が 5 件未満になる場合があります（サーバー側で 10 分間のメモリキャッシュあり）。
- ニュースの著作権は各配信元に帰属します。リンク先の配信条件に従ってください。

## デプロイ（任意）

- Node.js ランタイム（例: Render, Railway, Fly.io, Heroku 等）にそのまま配置可能です。
- 低トラフィック前提のため追加のキャッシュは不要ですが、CDN キャッシュ（例: `/api/news` を 1〜5 分）を挟むと安定します。

