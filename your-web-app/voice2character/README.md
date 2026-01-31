# VoiceScribe - 高精度音声文字起こしWebアプリケーション

## 概要

**VoiceScribe** は、大容量MP4動画（1000MB超）に対応した、高精度音声文字起こしWebアプリケーションです。

OpenAI Whisper Large-v3 を搭載し、日本語音声を高い精度でテキストに変換します。チャンク分割アップロード、リアルタイム進捗表示、多形式エクスポートなど、SaaSレベルの機能を備えたフルスタック構成のアプリケーションです。

---

## 主な機能

| 機能 | 説明 |
|------|------|
| チャンク分割アップロード | 100MBチャンク単位でファイルを分割送信。最大5GBまで対応 |
| リアルタイム進捗表示 | WebSocket通信により、処理の各ステップを即座にUIへ反映 |
| 多形式エクスポート | TXT, SRT, VTT, JSON, TSV の5形式に対応 |
| ドラッグ&ドロップ | ファイルのドラッグ&ドロップによる直感的なアップロード |
| ダークモード対応 | ライト/ダークの切り替え。システム設定の自動検出にも対応 |
| レスポンシブデザイン | デスクトップからモバイルまで、あらゆる画面サイズに対応 |
| テキスト検索 | 文字起こし結果内のテキスト検索とハイライト表示 |
| 信頼度スコア表示 | 各セグメントの信頼度を表示し、低信頼度箇所を視覚的にマーキング |
| 多言語対応 | 日本語、英語、中国語、韓国語など複数言語の文字起こしに対応 |

---

## 技術スタック

### バックエンド

| 技術 | バージョン | 用途 |
|------|-----------|------|
| Python | 3.11 | 実行環境 |
| FastAPI | 0.109.2 | Webフレームワーク（非同期対応） |
| OpenAI Whisper | large-v3 | 音声文字起こしモデル |
| FFmpeg | - | 動画/音声ファイルからの音声抽出 |
| Celery | 5.3.6 | 非同期タスク処理（バックグラウンドワーカー） |
| Redis | 7 | タスクキュー・結果バックエンド・Pub/Sub |
| PostgreSQL | 16 | データベース（ジョブ・セグメント管理） |
| SQLAlchemy | 2.0.27 | ORM（非同期セッション対応） |
| Pydantic | 2.6.1 | データバリデーション・設定管理 |
| PyTorch | >= 2.0.0 | Whisperモデル推論エンジン |

### フロントエンド

| 技術 | バージョン | 用途 |
|------|-----------|------|
| Next.js | 14.1.0 | Reactフレームワーク（App Router） |
| React | 18.2.x | UIライブラリ |
| TypeScript | 5.3.x | 型安全な開発 |
| Tailwind CSS | 3.4.x | ユーティリティファーストCSS |
| lucide-react | 0.344.x | アイコンライブラリ |
| clsx | 2.1.x | 条件付きクラス名結合 |

### インフラ

| 技術 | 用途 |
|------|------|
| Docker / Docker Compose | コンテナ化・オーケストレーション |
| Nginx | リバースプロキシ（API/WebSocket/フロントエンドの統合） |
| NVIDIA GPU (CUDA) | Whisperモデルの高速推論（オプション） |

---

## 前提条件

- **Docker Desktop** がインストールされていること
- **Docker Compose v2** 以上
- （推奨）**NVIDIA GPU** と **NVIDIA Container Toolkit**
  - GPUがない場合はCPUモードで動作します（処理に時間がかかります）

---

## セットアップ手順

### 1. 環境変数の設定

`.env.example` をコピーして `.env` を作成し、必要に応じて編集します。

```bash
cp .env.example .env
```

`.env` ファイルの主な設定項目:

| 変数名 | 説明 | デフォルト値 |
|--------|------|-------------|
| `DATABASE_URL` | PostgreSQL接続URL | `postgresql+asyncpg://postgres:postgres@db:5432/voice2character` |
| `REDIS_URL` | Redis接続URL | `redis://redis:6379/0` |
| `UPLOAD_DIR` | アップロードファイル保存先 | `/app/data/uploads` |
| `PROCESSED_DIR` | 処理済みファイル保存先 | `/app/data/processed` |
| `MAX_FILE_SIZE` | 最大ファイルサイズ（バイト） | `5368709120`（5GB） |
| `WHISPER_MODEL` | 使用するWhisperモデル | `large-v3` |
| `WHISPER_DEVICE` | 推論デバイス（auto/cuda/cpu） | `auto` |
| `CORS_ORIGINS` | CORS許可オリジン | `["http://localhost:3000"]` |

### 2. Docker Composeによる起動

```bash
docker compose up -d --build
```

初回起動時は、Whisper large-v3モデルのダウンロード（約3GB）を含むビルドが実行されるため、時間がかかります。

### 3. アクセス

| サービス | URL |
|----------|-----|
| フロントエンド | http://localhost:3000 |
| バックエンドAPI | http://localhost:8000 |
| APIドキュメント（Swagger UI） | http://localhost:8000/docs |
| APIドキュメント（ReDoc） | http://localhost:8000/redoc |

### GPU非搭載環境での起動

`docker-compose.yml` 内の `backend` サービスと `worker` サービスにある以下の `deploy` セクションをコメントアウトしてください。

```yaml
# deploy:
#   resources:
#     reservations:
#       devices:
#         - driver: nvidia
#           count: all
#           capabilities: [gpu]
```

---

## 使い方

### ファイルのアップロード

1. トップページのドラッグ&ドロップエリアにファイルをドロップします。または「クリックしてファイルを選択」でファイルを選択します。
2. 文字起こし言語を選択します（デフォルト: 自動検出）。
   - 日本語、英語、中国語、韓国語から選択可能です。
3. 「アップロード開始」ボタンをクリックします。
4. アップロードの進捗（%、転送速度、残り時間）がリアルタイムに表示されます。

### 処理の進捗確認

- アップロード完了後、自動的にジョブ詳細ページに遷移します。
- 円形プログレスバーとステップインジケーターで、リアルタイムに処理状況を確認できます。
- 処理ステップ:
  1. **アップロード** (0% - 10%) --- ファイルのアップロードとチャンク結合
  2. **音声抽出** (15% - 30%) --- FFmpegによるWAV変換（16kHz, モノラル）
  3. **文字起こし** (35% - 90%) --- Whisper Large-v3による音声認識
  4. **完了** (100%) --- セグメントのDB保存と結果表示

### 結果の確認とエクスポート

- **タイムスタンプ付きのテキスト表示**: 各セグメントに開始時間・終了時間を表示
- **テキスト検索**: キーワードでセグメントをフィルタリング、ハイライト表示
- **表示モード切替**: セグメント表示 / フルテキスト表示を切り替え可能
- **全文コピー**: ワンクリックでクリップボードにコピー
- **5種類のフォーマットでエクスポート**:
  - **TXT** --- プレーンテキスト（タイムスタンプ付き）
  - **SRT** --- SubRip字幕形式（動画編集ソフト向け）
  - **VTT** --- WebVTT字幕形式（Webプレイヤー向け）
  - **JSON** --- 構造化データ（プログラム処理向け）
  - **TSV** --- タブ区切り（スプレッドシート分析向け）

---

## APIリファレンス

### アップロード関連

| メソッド | エンドポイント | 説明 |
|----------|---------------|------|
| `POST` | `/api/upload/init` | アップロード初期化（ジョブ作成） |
| `POST` | `/api/upload/{job_id}/chunk` | チャンクアップロード |
| `POST` | `/api/upload/{job_id}/complete` | アップロード完了（タスクキューイング） |

### ジョブ管理

| メソッド | エンドポイント | 説明 |
|----------|---------------|------|
| `GET` | `/api/jobs` | ジョブ一覧取得（ページネーション対応） |
| `GET` | `/api/jobs/{job_id}` | ジョブ詳細取得 |
| `GET` | `/api/jobs/{job_id}/transcription` | 文字起こし結果取得（全セグメント付き） |
| `DELETE` | `/api/jobs/{job_id}` | ジョブ削除（関連ファイル含む） |

### エクスポート

| メソッド | エンドポイント | 説明 |
|----------|---------------|------|
| `GET` | `/api/export/{job_id}?format={format}` | 文字起こし結果のファイルダウンロード |

### その他

| メソッド | エンドポイント | 説明 |
|----------|---------------|------|
| `GET` | `/api/health` | ヘルスチェック（DB・Redis接続状態含む） |
| `WebSocket` | `/ws/{job_id}` | 進捗のリアルタイム通知 |

詳細なAPIドキュメントは、起動後に http://localhost:8000/docs で確認できます。

---

## プロジェクト構成

```
voice2character/
├── .env.example                 # 環境変数テンプレート
├── .gitignore                   # Git除外設定
├── docker-compose.yml           # Docker Compose構成ファイル
│
├── backend/                     # バックエンド（Python / FastAPI）
│   ├── Dockerfile               # マルチステージビルド（Whisperモデル事前ダウンロード含む）
│   ├── requirements.txt         # Python依存パッケージ
│   └── app/
│       ├── __init__.py          # パッケージ初期化（バージョン情報）
│       ├── config.py            # 環境変数ベースの設定管理（pydantic-settings）
│       ├── database.py          # SQLAlchemy非同期エンジン・セッション管理
│       ├── main.py              # FastAPIアプリケーションエントリーポイント
│       ├── models/
│       │   ├── __init__.py      # モデルパッケージ
│       │   └── job.py           # Job, TranscriptionSegmentテーブル定義
│       ├── schemas/
│       │   ├── __init__.py      # スキーマパッケージ
│       │   └── job.py           # Pydanticリクエスト/レスポンススキーマ
│       ├── api/
│       │   ├── __init__.py      # APIルーター集約（/apiプレフィックス）
│       │   ├── websocket.py     # WebSocket接続管理（ConnectionManager）
│       │   └── routes/
│       │       ├── __init__.py  # ルートパッケージ
│       │       ├── upload.py    # アップロードAPI（init, chunk, complete）
│       │       ├── jobs.py      # ジョブ管理API（一覧, 詳細, 結果, 削除）
│       │       └── export.py    # エクスポートAPI（5形式対応）
│       ├── services/
│       │   ├── __init__.py      # サービスパッケージ
│       │   ├── audio_extractor.py  # FFmpegによる音声抽出（16kHz WAV変換）
│       │   ├── transcriber.py   # Whisper文字起こしサービス（シングルトン）
│       │   ├── file_manager.py  # チャンクアップロード・ファイル管理
│       │   └── export_service.py   # 5形式のエクスポート変換
│       └── workers/
│           ├── __init__.py      # Celeryアプリケーション初期化
│           └── tasks.py         # 文字起こし処理タスク（パイプライン定義）
│
├── frontend/                    # フロントエンド（Next.js / TypeScript）
│   ├── Dockerfile               # マルチステージビルド（standalone出力）
│   ├── package.json             # Node.js依存パッケージ
│   ├── next.config.js           # Next.js設定（APIプロキシ）
│   ├── tsconfig.json            # TypeScript設定
│   ├── postcss.config.js        # PostCSS設定
│   ├── tailwind.config.ts       # Tailwind CSS設定（ダークモード・カスタムカラー）
│   ├── types/
│   │   └── index.ts             # 共通型定義（Job, Transcription, ProgressMessage等）
│   ├── lib/
│   │   ├── api.ts               # API通信ライブラリ（fetch/XHRラッパー）
│   │   └── websocket.ts         # WebSocket管理（自動再接続・指数バックオフ）
│   ├── app/
│   │   ├── globals.css          # グローバルCSS（Tailwind指令・カスタムアニメーション）
│   │   ├── layout.tsx           # ルートレイアウト（ダークモードContext・Header・Footer）
│   │   ├── page.tsx             # トップページ（ヒーロー・アップローダー・ジョブ一覧・機能紹介）
│   │   └── jobs/
│   │       └── [id]/
│   │           └── page.tsx     # ジョブ詳細ページ（進捗・結果・エクスポート）
│   └── components/
│       ├── Header.tsx           # ヘッダー（ロゴ・ナビ・ダークモード切替）
│       ├── FileUploader.tsx     # ファイルアップローダー（D&D・チャンクアップロード）
│       ├── JobList.tsx          # ジョブ一覧（カード表示・ページネーション・削除）
│       ├── ProgressTracker.tsx  # 進捗表示（円形プログレス・ステップインジケーター）
│       ├── TranscriptionViewer.tsx  # 文字起こし結果表示（検索・コピー・モード切替）
│       └── ExportPanel.tsx      # エクスポートパネル（5形式・プレビュー・ダウンロード）
│
└── docker/                      # Docker関連設定ファイル
    ├── nginx.conf               # Nginxリバースプロキシ設定
    └── redis.conf               # Redis設定（AOF永続化・メモリ制限）
```

---

## 対応ファイル形式

### 動画形式

| 形式 | 拡張子 |
|------|--------|
| MPEG-4 | `.mp4` |
| Audio Video Interleave | `.avi` |
| QuickTime | `.mov` |
| Matroska | `.mkv` |
| WebM | `.webm` |

### 音声形式

| 形式 | 拡張子 |
|------|--------|
| MPEG-4 Audio | `.m4a` |
| MPEG Audio Layer III | `.mp3` |
| Waveform Audio | `.wav` |
| Free Lossless Audio Codec | `.flac` |

---

## トラブルシューティング

### Docker関連

| 問題 | 解決方法 |
|------|---------|
| ビルドが非常に遅い | Whisper large-v3モデル（約3GB）のダウンロードに時間がかかります。初回のみ発生します。 |
| GPUが認識されない | NVIDIA Container Toolkitがインストールされているか確認してください。`docker compose.yml`の`deploy`セクションを確認してください。 |
| GPUがない環境で起動できない | `docker-compose.yml`内のbackendとworkerの`deploy`セクションをコメントアウトしてください。 |
| コンテナが起動しない | `docker compose logs <サービス名>`でログを確認してください。 |
| DBに接続できない | PostgreSQLコンテナのヘルスチェックが完了するまで待ってください。`docker compose ps`で状態を確認できます。 |

### アップロード関連

| 問題 | 解決方法 |
|------|---------|
| アップロードが途中で失敗する | ネットワーク接続を確認してください。チャンク分割アップロードにより、途中で接続が切れてもリトライ可能です。 |
| ファイルが大きすぎるエラー | 最大ファイルサイズは5GBです。`MAX_FILE_SIZE`環境変数で変更可能です。 |
| 対応していないファイル形式エラー | 対応形式（MP4, AVI, MOV, MKV, WebM, M4A, MP3, WAV, FLAC）を確認してください。 |

### 文字起こし関連

| 問題 | 解決方法 |
|------|---------|
| 文字起こしの精度が低い | 音声の品質を確認してください。ノイズが多い場合や話者が複数の場合、精度が低下することがあります。言語設定が正しいか確認してください。 |
| 処理に非常に時間がかかる | GPU未使用の場合、CPUモードでは処理に長時間かかります。NVIDIA GPUの利用を推奨します。 |
| 処理がfailedになる | `docker compose logs worker`でCeleryワーカーのログを確認してください。メモリ不足やディスク容量不足が原因の場合があります。 |

### WebSocket関連

| 問題 | 解決方法 |
|------|---------|
| 進捗がリアルタイムに更新されない | ブラウザのWebSocket接続が有効か確認してください。ページ右上の接続インジケーターを確認してください。 |
| 「オフライン」と表示される | WebSocket接続が切断されています。自動再接続（最大10回、指数バックオフ）が試行されます。ページを再読み込みしてください。 |

---

## ライセンス

MIT License

Copyright (c) 2024 VoiceScribe

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
