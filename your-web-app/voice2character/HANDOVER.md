# VoiceScribe 開発引継資料

本資料は、VoiceScribeプロジェクトを他のチャットセッションやAIアシスタントで開発を継続するための詳細な引継資料です。

---

## 1. プロジェクト概要

### 目的

大容量MP4動画（1000MB超）に対応した、高精度音声文字起こしWebアプリケーションの開発。
OpenAI Whisper Large-v3を使用し、日本語を中心とした多言語の音声をテキストに変換する。

### 要件

- 1000MBを超える動画ファイルのアップロードに対応すること
- チャンク分割アップロードにより、大容量ファイルを安定的に処理すること
- Whisper Large-v3を使用した高精度な日本語文字起こし
- WebSocketによるリアルタイム進捗通知
- 5種類のエクスポート形式（TXT, SRT, VTT, JSON, TSV）
- ダークモード・レスポンシブ対応のモダンなUI
- Docker Composeによるワンコマンド起動

### 技術的判断の根拠

| 判断 | 理由 |
|------|------|
| FastAPI（非同期） | 大容量ファイルのアップロード処理に適した非同期I/O。自動API文書生成。 |
| Celery + Redis | 文字起こしは重い処理のため、バックグラウンドワーカーで非同期実行。Redis Pub/Subで進捗通知。 |
| PostgreSQL | ジョブ・セグメントのリレーショナルデータ管理。カスケード削除によるデータ整合性。 |
| Next.js 14 (App Router) | SSR対応のReactフレームワーク。App Routerによるファイルベースルーティング。 |
| Whisper Large-v3 | 日本語音声認識で現時点最高精度のオープンソースモデル。 |
| チャンクアップロード | ブラウザのメモリ制限とネットワーク切断に対応するため、100MB単位で分割送信。 |
| Docker マルチステージビルド | Whisperモデルの事前ダウンロード、ビルド成果物の最適化、セキュリティ（非rootユーザー）。 |

---

## 2. アーキテクチャ概要

### 全体構成図

```
+-------------------+     +-------------------+     +-------------------+
|                   |     |                   |     |                   |
|   ブラウザ        |<--->|   Frontend        |<--->|   Backend         |
|   (React SPA)     |     |   (Next.js:3000)  |     |   (FastAPI:8000)  |
|                   |     |                   |     |                   |
+-------------------+     +-------------------+     +--------+----------+
                                                             |
                                    +------------------------+------------------------+
                                    |                        |                        |
                          +---------v---------+    +---------v---------+    +---------v---------+
                          |                   |    |                   |    |                   |
                          |   PostgreSQL      |    |   Redis           |    |   Celery Worker   |
                          |   (DB:5432)       |    |   (Cache:6379)    |    |   (Whisper処理)   |
                          |                   |    |                   |    |                   |
                          +-------------------+    +-------------------+    +-------------------+
```

### コンポーネント間のデータフロー

```
[ブラウザ]
   |
   | (1) POST /api/upload/init   --- ジョブ作成
   | (2) POST /api/upload/{id}/chunk  --- チャンクアップロード x N回
   | (3) POST /api/upload/{id}/complete --- アップロード完了通知
   |
[FastAPI バックエンド]
   |
   | (4) Celeryタスクキューに投入  (process_transcription_task.delay)
   |
[Redis (ブローカー)]
   |
   | (5) ワーカーがタスクを取得
   |
[Celery Worker]
   |
   | (6) FFmpeg: 音声抽出 (MP4 -> WAV 16kHz mono)
   | (7) Whisper: 文字起こし (WAV -> セグメント)
   | (8) DB保存: TranscriptionSegment レコード作成
   | (9) Redis Pub/Sub: 進捗更新を発行
   |
[Redis Pub/Sub]
   |
   | (10) FastAPIのWebSocketハンドラが受信（※現在は直接通知方式）
   |
[WebSocket /ws/{job_id}]
   |
   | (11) ブラウザにリアルタイム進捗を送信
   |
[ブラウザ]
   |
   | (12) GET /api/jobs/{id}/transcription --- 結果取得
   | (13) GET /api/export/{id}?format=srt  --- エクスポート
```

### 処理パイプライン

```
アップロード       音声抽出          文字起こし         結果保存
(0-10%)           (15-30%)         (35-90%)          (90-100%)

[チャンク受信] -> [FFmpeg変換] -> [Whisper推論] -> [DB保存]
     |                |                |               |
     v                v                v               v
 uploading       extracting      transcribing      completed
     |                |                |               |
     +--- WebSocket進捗通知 ---+---  Redis Pub/Sub ---+
```

---

## 3. ディレクトリ構成と各ファイルの役割

### ルートディレクトリ

| ファイル | 役割 |
|----------|------|
| `.env.example` | 環境変数のテンプレート。DATABASE_URL, REDIS_URL, WHISPER_MODEL等 |
| `.gitignore` | Git除外設定。node_modules, .next, __pycache__, data/, models/等 |
| `docker-compose.yml` | 全5サービス（frontend, backend, worker, db, redis）の構成定義 |

### backend/

| ファイル | 役割 |
|----------|------|
| `Dockerfile` | 3ステージビルド: (1)依存関係 (2)Whisperモデルプリダウンロード (3)本番イメージ |
| `requirements.txt` | Python依存パッケージ一覧（21パッケージ） |
| `app/__init__.py` | パッケージ初期化。`__version__ = "1.0.0"`, `__app_name__ = "Voice2Character"` |
| `app/config.py` | `Settings`クラス（pydantic-settings）。環境変数の読み込み、ディレクトリ作成、Whisperデバイス検出 |
| `app/database.py` | SQLAlchemy AsyncEngine/AsyncSession。`get_db()`依存性注入、`create_tables()`自動マイグレーション |
| `app/main.py` | FastAPIアプリ本体。ライフサイクル管理、CORS、ミドルウェア（リクエストID、アクセスログ）、ルーター登録、WebSocketエンドポイント、ヘルスチェック、例外ハンドラー |
| `app/models/__init__.py` | モデルパッケージ。Job, TranscriptionSegmentをエクスポート |
| `app/models/job.py` | `Job`テーブル（ジョブ管理）と`TranscriptionSegment`テーブル（セグメント管理）の定義 |
| `app/schemas/__init__.py` | スキーマパッケージ。全Pydanticスキーマをエクスポート |
| `app/schemas/job.py` | Pydanticスキーマ: JobCreate, UploadChunkRequest, ExportRequest, JobResponse, SegmentResponse, TranscriptionResponse, UploadInitResponse, ProgressUpdate。JobStatus/ExportFormat列挙型 |
| `app/api/__init__.py` | メインAPIルーター（`/api`プレフィックス）。upload, jobs, export, systemルーターを集約 |
| `app/api/routes/__init__.py` | ルートパッケージ |
| `app/api/routes/upload.py` | アップロードAPI: `POST /api/upload/init`, `POST /api/upload/{id}/chunk`, `POST /api/upload/{id}/complete` |
| `app/api/routes/jobs.py` | ジョブ管理API: `GET /api/jobs`, `GET /api/jobs/{id}`, `GET /api/jobs/{id}/transcription`, `DELETE /api/jobs/{id}` |
| `app/api/routes/export.py` | エクスポートAPI: `GET /api/export/{id}?format=txt\|srt\|vtt\|json\|tsv` |
| `app/api/routes/system.py` | システム情報API: `GET /api/system/info`。CPU/RAM/GPU検出、Whisperモデル推奨設定を返す |
| `app/api/websocket.py` | `ConnectionManager`クラス（シングルトン）。ジョブIDごとのWebSocket接続管理、進捗ブロードキャスト、ping/pong対応 |
| `app/services/__init__.py` | サービスパッケージ |
| `app/services/audio_extractor.py` | `AudioExtractor`クラス。FFmpegで音声抽出（16kHz, mono, PCM16）。ffprobeで長さ取得・メディア検証 |
| `app/services/system_info.py` | `SystemInfoService`クラス。psutil/torch.cudaによるハードウェア検出、Whisperモデル推奨エンジン。`WHISPER_MODELS`定数（モデルメタデータ一元管理） |
| `app/services/transcriber.py` | `TranscriberService`クラス（シングルトン + スレッドロック）。Whisperモデルロード・再ロード対応、文字起こし実行、セグメント整形。日本語最適化パラメータ（beam_size=5, temperature=0, VADフィルタ有効） |
| `app/services/file_manager.py` | `FileManager`クラス。チャンク保存・結合・削除、ジョブファイル全削除、ディスク容量確認 |
| `app/services/export_service.py` | `ExportService`クラス。TXT/SRT/VTT/JSON/TSVの5形式変換。タイムスタンプフォーマッタ（SRT: カンマ区切り、VTT: ドット区切り） |
| `app/workers/__init__.py` | Celeryアプリケーション初期化。ブローカー/バックエンドはRedis。`task_acks_late=True`, `worker_concurrency=1` |
| `app/workers/tasks.py` | `process_transcription_task` Celeryタスク。処理パイプライン全体の制御。同期DBセッション（psycopg2）、Redis Pub/Sub進捗通知、リトライ（最大3回） |

### frontend/

| ファイル | 役割 |
|----------|------|
| `Dockerfile` | 3ステージビルド: (1)依存関係 (2)Next.jsビルド (3)standalone実行環境 |
| `package.json` | Next.js 14.1.0, React 18, lucide-react, clsx, Tailwind CSS等 |
| `next.config.js` | APIプロキシ設定。`/api/*` -> `backend:8000`, `/ws/*` -> `backend:8000` |
| `tsconfig.json` | TypeScript厳格モード。パスエイリアス `@/*` |
| `postcss.config.js` | PostCSS + Tailwind CSS + autoprefixer |
| `tailwind.config.ts` | ダークモード（class戦略）、ブランドカラー（indigo系）、Noto Sans JPフォント、カスタムアニメーション6種 |
| `types/index.ts` | 共通型定義: Job, TranscriptionSegment, Transcription, UploadProgress, JobListResponse, ExportFormat, ProgressMessage, ApiError, UploadInitResponse, ChunkUploadResponse, CpuInfo, RamInfo, GpuInfo, WhisperModelInfo, SystemRecommendation, SystemInfo |
| `lib/api.ts` | API通信ライブラリ。fetch/XHRラッパー、チャンクアップロード進捗追跡（XMLHttpRequest）、エラーハンドリング（ApiRequestError）、`getSystemInfo()`（システム情報取得）、ユーティリティ（formatFileSize, formatDuration, formatDate） |
| `lib/websocket.ts` | `WebSocketManager`クラス。自動再接続（最大10回、指数バックオフ1秒-30秒+ジッター）、接続状態管理、進捗コールバック、リソースクリーンアップ |
| `app/globals.css` | Tailwind指令、ダークモードCSS、プログレスバーアニメーション（shimmer, stripes）、ドロップゾーン、ガラスモーフィズム、カスタムスクロールバー |
| `app/layout.tsx` | ルートレイアウト（`'use client'`）。DarkModeContext（localStorage + システム設定自動検出）、Header/Footer配置、Noto Sans JPフォント読み込み |
| `app/page.tsx` | トップページ。ヒーローセクション、FileUploader、JobList、機能紹介カード6種、対応形式一覧 |
| `app/jobs/[id]/page.tsx` | ジョブ詳細ページ。ジョブ情報カード、ProgressTracker、TranscriptionViewer、ExportPanel、WebSocket接続管理、ステータスバッジ、エラーリトライ |
| `components/Header.tsx` | ヘッダー。ロゴ（Mic SVG + "VoiceScribe"）、デスクトップ/モバイルナビ、ダークモードトグル、sticky + backdrop-blur |
| `components/FileUploader.tsx` | ファイルアップローダー。D&D対応、チャンク分割アップロード（100MB）、進捗バー（%/速度/残り時間）、言語・モデル・デバイス選択（3列グリッド）、キャンセル機能、アップロード完了後自動遷移 |
| `components/SystemInfoPanel.tsx` | システム環境情報パネル。CPU/RAM/GPU情報表示、推奨設定ハイライト、折りたたみ可能、ローディング・エラーハンドリング |
| `components/JobList.tsx` | ジョブ一覧。カード表示、ステータスバッジ（6種色分け）、ページネーション（8件/ページ）、削除（確認ダイアログ）、空状態表示 |
| `components/ProgressTracker.tsx` | 進捗表示。円形SVGプログレスバー、4ステップインジケーター（アップロード/音声抽出/文字起こし/完了）、接続線アニメーション、エラー/完了表示 |
| `components/TranscriptionViewer.tsx` | 結果表示。セグメント/フルテキスト表示切替、テキスト検索+ハイライト、全文コピー、信頼度スコア表示（低信頼度マーキング閾値70%）、統計情報、スクロールトップ |
| `components/ExportPanel.tsx` | エクスポート。5形式選択グリッド（アイコン付き）、形式説明、プレビュー表示（先頭5セグメント）、ダウンロードリンク |

### docker/

| ファイル | 役割 |
|----------|------|
| `nginx.conf` | Nginxリバースプロキシ。`/api/` -> backend:8000、`/ws/` -> backend:8000（WebSocket対応）、`/` -> frontend:3000。セキュリティヘッダー、gzip圧縮、5GB上限、600秒タイムアウト |
| `redis.conf` | Redis設定。512MBメモリ上限、LRUポリシー、AOF永続化（毎秒）、RDBスナップショット、最大100クライアント、スロークエリログ |

---

## 4. バックエンド詳細

### 4.1 FastAPI設定・起動フロー

```
1. app/main.py が uvicorn により起動される
2. lifespan() コンテキストマネージャーが実行される:
   a. settings.setup_directories() --- upload/processed/tmpディレクトリ作成
   b. create_tables() --- SQLAlchemy Base.metadata.create_all() でテーブル自動作成
3. ミドルウェア登録:
   a. CORSMiddleware --- クロスオリジン許可
   b. request_id_middleware --- UUID v4リクエストID付与
   c. access_log_middleware --- 処理時間ログ記録
4. ルーター登録:
   a. api_router (/api) --- upload, jobs, export
   b. WebSocket (/ws/{job_id}) --- websocket_endpoint
5. 例外ハンドラー登録:
   a. 500 グローバル例外ハンドラー（DEBUG時のみ詳細表示）
   b. 404 Not Found ハンドラー
```

起動コマンド（Dockerfile CMD）:
```
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

### 4.2 データベースモデル（ER図）

```
+---------------------------+          +-------------------------------+
|         jobs              |          |   transcription_segments      |
+---------------------------+          +-------------------------------+
| id        (PK, VARCHAR)   |<----+    | id            (PK, INTEGER)  |
| file_name (VARCHAR, NN)   |     |    | job_id        (FK -> jobs.id)|
| file_size (BIGINT, NN)    |     +----| segment_index (INTEGER, NN)  |
| file_path (VARCHAR)       |          | start_time    (FLOAT, NN)    |
| duration  (FLOAT)         |          | end_time      (FLOAT, NN)    |
| status    (VARCHAR, NN)   |          | text          (TEXT, NN)     |
| progress  (FLOAT)         |          | confidence    (FLOAT)        |
| error_message (VARCHAR)   |          +-------------------------------+
| language  (VARCHAR)       |
| whisper_model (VARCHAR)   |
| whisper_device (VARCHAR)  |
| created_at (TIMESTAMP TZ) |
| updated_at (TIMESTAMP TZ) |
| completed_at (TIMESTAMP TZ)|
+---------------------------+

リレーション: jobs 1 --- N transcription_segments
             CASCADE DELETE（ジョブ削除時にセグメントも削除）
```

**ステータス遷移図:**
```
uploading -> queued -> extracting -> transcribing -> completed
    |           |          |              |
    +-----------+----------+--------------+---> failed
```

### 4.3 APIエンドポイント一覧

#### アップロード関連 (`/api/upload`)

| メソッド | URL | パラメータ | レスポンス | 説明 |
|----------|-----|-----------|-----------|------|
| POST | `/api/upload/init` | Body: `{file_name, file_size, language, whisper_model?, whisper_device?}` | `{job_id, upload_url, chunk_size}` (201) | ジョブ作成。拡張子・サイズ検証。モデル・デバイス指定可 |
| POST | `/api/upload/{job_id}/chunk` | Query: `chunk_index, total_chunks`、Form: `file` (multipart) | `{status, chunk_index, total_chunks, message}` (200) | チャンク保存。進捗0-10% |
| POST | `/api/upload/{job_id}/complete` | Query: `total_chunks` | `JobResponse` (200) | チャンク結合、Celeryタスク投入、ステータスqueued |

#### ジョブ管理 (`/api/jobs`)

| メソッド | URL | パラメータ | レスポンス | 説明 |
|----------|-----|-----------|-----------|------|
| GET | `/api/jobs` | Query: `page (default:1), page_size (default:20, max:100)` | `{jobs[], total, page, page_size, total_pages}` | ジョブ一覧（作成日時降順） |
| GET | `/api/jobs/{job_id}` | Path: `job_id` | `JobResponse` | ジョブ詳細 |
| GET | `/api/jobs/{job_id}/transcription` | Path: `job_id` | `{job_id, file_name, duration, language, status, segments[], full_text}` | 文字起こし結果（selectinload） |
| DELETE | `/api/jobs/{job_id}` | Path: `job_id` | `{status, message}` | ジョブ削除（ファイル+DB） |

#### エクスポート (`/api/export`)

| メソッド | URL | パラメータ | レスポンス | 説明 |
|----------|-----|-----------|-----------|------|
| GET | `/api/export/{job_id}` | Query: `format (txt\|srt\|vtt\|json\|tsv)` | StreamingResponse (ファイルダウンロード) | completedジョブのみ |

#### その他

| メソッド | URL | レスポンス | 説明 |
|----------|-----|-----------|------|
| GET | `/api/system/info` | `{cpu, ram, gpu, whisper_models[], recommendation}` | サーバー環境情報・Whisperモデル推奨設定 |
| GET | `/api/health` | `{status, app, version, whisper_model, database, redis}` | ヘルスチェック |
| WebSocket | `/ws/{job_id}` | JSON: `{job_id, status, progress, message}` | 進捗リアルタイム通知 |

### 4.4 サービス層の構成

#### AudioExtractor (`app/services/audio_extractor.py`)

- FFmpegによる音声抽出。Whisper互換フォーマット（16kHz, モノラル, 16bit PCM WAV）に変換。
- `extract_audio(input_path, output_path)` --- 音声変換
- `get_duration(file_path)` --- ffprobeで長さ取得
- `validate_media_file(file_path)` --- メディアファイル検証（音声トラック有無）

#### TranscriberService (`app/services/transcriber.py`)

- **シングルトンパターン** + `threading.Lock` によるスレッドセーフ性。
- モデルは初回呼び出し時にロード。以降は同じmodel+deviceなら再利用、異なる場合は自動再ロード。
- `load_model(model_name, device, download_root)` --- Whisperモデルロード（同一設定時はスキップ、異なる場合は`_unload_model()`後に再ロード）
- `_unload_model()` --- モデル解放 + `torch.cuda.empty_cache()`でGPUメモリ解放
- `transcribe(audio_path, language, progress_callback)` --- 文字起こし実行
- `current_model_name` / `current_device` --- 現在ロード中のモデル名・デバイス（プロパティ）
- **日本語最適化パラメータ:**
  - `beam_size=5`, `best_of=5` --- 精度重視
  - `temperature=0` --- 決定的生成
  - `initial_prompt="以下は日本語の音声の書き起こしです。"` --- 日本語コンテキスト
  - `condition_on_previous_text=True` --- 前テキスト参照
  - `fp16=True` (GPU時) --- FP16高速化
  - `vad_filter=True` --- 無音区間検出フィルタ
  - VADパラメータ: `threshold=0.5`, `min_speech_duration_ms=250`, `min_silence_duration_ms=1000`
- 信頼度スコア: `1.0 - no_speech_prob` で計算

#### FileManager (`app/services/file_manager.py`)

- チャンク保存ディレクトリ: `{TEMP_DIR}/chunks_{job_id}/chunk_{index:06d}`
- `save_chunk(job_id, chunk_index, chunk_data)` --- 非同期ファイル書き込み（aiofiles）
- `merge_chunks(job_id, total_chunks, original_filename)` --- チャンク結合（1MB単位の読み書き）
- `cleanup_chunks(job_id)` --- 一時チャンク削除
- `cleanup_job_files(job_id)` --- ジョブ関連全ファイル削除
- `check_disk_space(required_bytes)` --- ディスク容量確認（必要容量の2倍を確保）

#### ExportService (`app/services/export_service.py`)

- `export(segments, format)` --- フォーマットハンドラーへのディスパッチ
- `export_txt` --- `[MM:SS - MM:SS] テキスト` 形式
- `export_srt` --- SubRip形式（`HH:MM:SS,mmm`、カンマ区切り）
- `export_vtt` --- WebVTT形式（`HH:MM:SS.mmm`、ドット区切り、WEBVTTヘッダー付き）
- `export_json` --- `{segments: [{index, start, end, text, confidence}], full_text}` 形式
- `export_tsv` --- ヘッダー行付きタブ区切り

### 4.5 Celeryタスク処理フロー

#### Celeryアプリケーション設定 (`app/workers/__init__.py`)

- ブローカー: `redis://localhost:6379/0`
- 結果バックエンド: `redis://localhost:6379/1`
- シリアライゼーション: JSON
- タイムゾーン: Asia/Tokyo
- `task_acks_late=True` --- タスク完了後にACK（ワーカー障害時の再実行保証）
- `worker_prefetch_multiplier=1` --- 1タスクずつ取得（大量メモリ消費タスク向け）
- `worker_concurrency=1` --- 同時実行数1（Whisperのメモリ消費が大きいため）
- リトライ: 最大3回、間隔60秒

#### 処理パイプライン (`app/workers/tasks.py`)

```
process_transcription_task(job_id):
    |
    | (1) 同期DBセッション取得 (psycopg2)
    | (2) ジョブ情報取得、file_path確認
    |
    | === ステップ2: 音声抽出 (15%-30%) ===
    | (3) ステータス -> "extracting"
    | (4) audio_extractor.get_duration() で長さ取得
    | (5) audio_extractor.extract_audio() で WAV変換
    |     -> asyncio.new_event_loop() で同期的にasync関数を実行
    | (6) Redis Pub/Sub で進捗通知
    |
    | === ステップ3: 文字起こし (35%-90%) ===
    | (7) ステータス -> "transcribing"
    | (7.5) ジョブのwhisper_model/whisper_deviceを取得（null時はサーバー設定にフォールバック）
    | (8) TranscriberService().load_model() (初回 or モデル/デバイス変更時に再ロード)
    | (9) transcriber.transcribe() 実行
    |     -> progress_callback で進捗を35%-90%にマッピング
    |
    | === ステップ4: 結果保存 (90%-100%) ===
    | (10) TranscriptionSegment レコードをバルク作成
    | (11) session.commit()
    |
    | === ステップ5: 完了処理 ===
    | (12) ステータス -> "completed", progress=100%
    | (13) completed_at を設定
    | (14) Redis Pub/Sub で完了通知
    |
    | === エラー時 ===
    | (E1) ステータス -> "failed"
    | (E2) error_message を設定
    | (E3) self.retry(exc=e) でリトライ (max_retries以下の場合)
    |
    | === finally ===
    | (F1) session.close()
```

#### 進捗更新のメカニズム

```
[Celery Worker]
     |
     | (1) _update_job_status() --- DBのJobレコードを直接更新（同期セッション）
     | (2) _send_progress_via_websocket() --- Redis Pub/Subチャンネルにメッセージ発行
     |     -> チャンネル名: "job_progress:{job_id}"
     |     -> メッセージ: JSON {job_id, status, progress, message}
     |
[Redis Pub/Sub]
     |
     | (※現在の実装では、WebSocket側でPub/Subをsubscribeする仕組みは
     |   未実装。クライアントはポーリングまたは直接WebSocket接続で
     |   FastAPIプロセス内のConnectionManagerから通知を受ける)
```

#### エラーハンドリングとリトライ

- Celeryの`bind=True`でタスクインスタンスを参照可能
- `max_retries=3`, `default_retry_delay=60`秒
- リトライ可能な場合: `self.retry(exc=e)` で再キューイング
- リトライ上限到達時: ステータスを`failed`に更新してタスク終了
- WebSocket通知失敗はタスク処理を停止しない（`try/except`で保護）

### 4.6 WebSocket通信

#### ConnectionManager (`app/api/websocket.py`)

- **シングルトンインスタンス**: `manager = ConnectionManager()`
- ジョブIDをキー、WebSocket接続リストを値とする辞書で管理
- `connect(websocket, job_id)` --- 接続受付・登録
- `disconnect(websocket, job_id)` --- 切断・登録解除
- `send_progress(job_id, update)` --- 指定ジョブの全接続に進捗送信（切断済み接続は自動除外）
- `broadcast(message)` --- 全接続にメッセージ送信
- ping/pongメッセージ対応（keepalive）

#### WebSocketエンドポイント

```
URL: /ws/{job_id}
プロトコル: ws:// または wss://

接続フロー:
1. クライアントが接続
2. manager.connect() で登録
3. while True: クライアントからのメッセージ待機
4. "ping" 受信時は {"type": "pong"} を返信
5. WebSocketDisconnect で正常切断処理
```

#### Redis Pub/Subとの連携方式

- CeleryワーカーはFastAPIプロセスとは別プロセスで動作するため、直接WebSocketに送信できない。
- 現在の実装: Celeryワーカーから`redis.publish("job_progress:{job_id}", json_message)`でメッセージ発行。
- **注意**: FastAPI側でRedis Pub/SubをsubscribeしてWebSocketに中継する処理は現在未実装。クライアント側はジョブ詳細ページでポーリング（fetchJob）またはWebSocket接続で状態を確認している。

---

## 5. フロントエンド詳細

### 5.1 Next.js App Router構成

```
app/
├── globals.css          # グローバルCSS
├── layout.tsx           # ルートレイアウト（'use client'）
├── page.tsx             # / （トップページ）
└── jobs/
    └── [id]/
        └── page.tsx     # /jobs/{id} （ジョブ詳細ページ）
```

- 全ページが `'use client'` のクライアントコンポーネント
- `layout.tsx` で `DarkModeContext` を提供
- `next.config.js` で `/api/*` と `/ws/*` をbackend:8000にプロキシ

### 5.2 コンポーネント一覧と役割

| コンポーネント | 場所 | 役割 |
|---------------|------|------|
| `Header` | `components/Header.tsx` | グローバルヘッダー。ロゴ、ナビゲーション（ホーム/ジョブ一覧）、ダークモードトグル、モバイルメニュー。sticky配置+backdrop-blur。 |
| `FileUploader` | `components/FileUploader.tsx` | ファイルアップロードUI。ドラッグ&ドロップ、ファイル選択、バリデーション、チャンク分割アップロード、進捗表示、言語選択、キャンセル機能。完了後自動遷移。 |
| `JobList` | `components/JobList.tsx` | ジョブ一覧表示。カード形式、ステータスバッジ（6種色分け）、ファイルサイズ・日時表示、ページネーション（8件/ページ）、削除確認ダイアログ。 |
| `ProgressTracker` | `components/ProgressTracker.tsx` | 処理進捗表示。SVG円形プログレスバー、4ステップインジケーター（接続線アニメーション付き）、ステータスメッセージ、エラー/完了表示。 |
| `TranscriptionViewer` | `components/TranscriptionViewer.tsx` | 文字起こし結果表示。セグメント/フルテキスト切替、テキスト検索+ハイライト、全文コピー、低信頼度セグメントマーキング（閾値70%）、統計情報。 |
| `ExportPanel` | `components/ExportPanel.tsx` | エクスポートUI。5形式選択グリッド、形式説明、プレビュー（先頭5セグメント）、ダウンロードリンク。 |

### 5.3 API通信ライブラリ (`lib/api.ts`)

- ベースURL: `/api`（Next.jsプロキシ経由）
- `ApiRequestError`クラス: HTTPステータスコード+エラー詳細をラップ
- `handleResponse<T>()`: レスポンスバリデーション共通関数
- 主要関数:
  - `initUpload(fileName, fileSize, language, whisperModel?, whisperDevice?)` --- アップロード初期化（モデル・デバイス指定対応）
  - `uploadChunk(jobId, chunkIndex, totalChunks, chunk, onProgress?)` --- チャンク送信（XMLHttpRequestで進捗追跡）
  - `completeUpload(jobId, totalChunks)` --- アップロード完了
  - `getJobs(page, pageSize)` --- ジョブ一覧
  - `getJob(jobId)` --- ジョブ詳細
  - `getTranscription(jobId)` --- 文字起こし結果
  - `deleteJob(jobId)` --- ジョブ削除
  - `getExportUrl(jobId, format)` --- エクスポートURL生成
  - `getSystemInfo()` --- サーバー環境情報取得（CPU/RAM/GPU/推奨設定）
- ユーティリティ:
  - `formatFileSize(bytes)` --- ファイルサイズ表示
  - `formatDuration(seconds)` --- 時間表示
  - `formatDate(dateStr)` --- 日本語日付表示

### 5.4 WebSocket管理 (`lib/websocket.ts`)

- `WebSocketManager`クラス:
  - `connect(jobId)` --- WebSocket接続開始
  - `disconnect()` --- 意図的切断
  - `onProgress(callback)` --- 進捗コールバック登録（登録解除関数を返す）
  - `onStateChange(callback)` --- 接続状態変更コールバック登録
  - `destroy()` --- 全リソース解放
- 接続状態: `'connecting' | 'connected' | 'disconnected' | 'error'`
- 自動再接続:
  - 最大10回試行
  - 指数バックオフ: `min(1000 * 2^attempts, 30000) + random(0-1000)` ミリ秒
  - 意図的切断時は再接続しない
- WebSocket URL構築: `ws://` or `wss://` + `window.location.host` + `/ws/jobs/{jobId}/progress`

### 5.5 チャンクアップロードの実装詳細

**フロントエンド側（`FileUploader.tsx`）:**

```
1. ファイルバリデーション（拡張子、サイズ上限5GB、空ファイルチェック）
2. initUpload() でジョブ作成、job_id取得
3. ファイルを CHUNK_SIZE (100MB) 単位でスライス
4. for each chunk:
   a. abortControllerRefでキャンセルチェック
   b. file.slice(start, end) でBlobを切り出し
   c. uploadChunk() でFormData送信
      - XMLHttpRequest使用（upload.onprogressで進捗追跡）
      - 転送速度・残り時間をリアルタイム計算
5. completeUpload() でチャンク結合+タスクキューイング
6. 完了後1秒待ってrouter.push(`/jobs/${job_id}`)
```

**バックエンド側:**

```
1. POST /api/upload/init
   - JobCreate スキーマでバリデーション
   - is_allowed_extension() で拡張子チェック
   - MAX_FILE_SIZE でサイズチェック
   - Job レコード作成（status="uploading"、whisper_model/whisper_device保存）
   - 返却: {job_id, upload_url, chunk_size}

2. POST /api/upload/{job_id}/chunk?chunk_index=N&total_chunks=M
   - ジョブ存在・ステータス確認
   - chunk_index 範囲チェック
   - file_manager.save_chunk() で一時ディレクトリに保存
   - 進捗率更新（0-10%にマッピング）

3. POST /api/upload/{job_id}/complete?total_chunks=M
   - file_manager.merge_chunks() で全チャンクを結合
   - file_manager.cleanup_chunks() で一時ファイル削除
   - Celeryタスク投入: process_transcription_task.delay(job_id)
   - ステータス -> "queued", progress=10%
```

### 5.6 状態管理（useStateの構成）

**layout.tsx (ルートレイアウト):**
- `isDark: boolean` --- ダークモード状態
- `mounted: boolean` --- ハイドレーション制御
- `DarkModeContext` でアプリ全体に提供

**FileUploader.tsx:**
- `isDragOver: boolean` --- ドラッグオーバー状態
- `uploads: FileUploadState[]` --- アップロードファイル一覧（各ファイルのstatus, progress, jobId, error）
- `language: string` --- 選択言語
- `whisperModel: string` --- 選択Whisperモデル（推奨値で初期化）
- `whisperDevice: string` --- 選択デバイス（'auto' / 'cpu' / 'cuda'、推奨値で初期化）
- `systemInfo: SystemInfo | null` --- サーバー環境情報（マウント時に取得）
- `abortControllerRef: Map<string, boolean>` --- キャンセルフラグ管理

**JobList.tsx:**
- `jobs: PaginatedResponse<Job> | null` --- ジョブ一覧データ
- `currentPage: number` --- 現在のページ
- `isLoading / error` --- ローディング・エラー状態
- `deletingJobId / showDeleteConfirm` --- 削除UI状態

**jobs/[id]/page.tsx (ジョブ詳細):**
- `job: Job | null` --- ジョブ情報
- `transcription: Transcription | null` --- 文字起こし結果
- `isLoading / error` --- ローディング・エラー状態
- `wsState: ConnectionState` --- WebSocket接続状態
- `wsManagerRef: WebSocketManager | null` --- WebSocketマネージャー

---

## 6. Docker構成

### 6.1 各サービスの役割

| サービス | イメージ | ポート | 役割 |
|---------|---------|--------|------|
| `frontend` | カスタム (node:20-alpine) | 3000 | Next.js Webフロントエンド |
| `backend` | カスタム (python:3.11-slim) | 8000 | FastAPI バックエンドAPI |
| `worker` | backendと同じイメージ | - | Celeryワーカー（文字起こし処理） |
| `db` | postgres:16-alpine | 5432 | PostgreSQLデータベース |
| `redis` | redis:7-alpine | 6379 | タスクキュー・結果バックエンド |

### 6.2 ネットワーク構成

- 単一のブリッジネットワーク: `app-network`
- 全サービスが同一ネットワーク内で通信
- ホスト名でのサービス間通信: `db`, `redis`, `backend`, `frontend`

### 6.3 ボリュームマウント

| ボリューム名 | マウント先 | 用途 |
|-------------|-----------|------|
| `postgres-data` | `/var/lib/postgresql/data` | PostgreSQLデータ永続化 |
| `redis-data` | `/data` | Redisデータ永続化（AOF/RDB） |
| `upload-data` | `/app/data` | アップロードファイル・処理済みファイル（backend/worker共有） |

### 6.4 GPU設定

backendとworkerサービスに以下のdeploy設定が含まれています:

```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: all
          capabilities: [gpu]
```

GPUが利用できない環境ではこのセクションをコメントアウトする必要があります。

### 6.5 依存関係とヘルスチェック

```
frontend -> backend
backend  -> db (condition: service_healthy), redis (condition: service_healthy)
worker   -> db (condition: service_healthy), redis (condition: service_healthy)
```

- PostgreSQL: `pg_isready -U postgres` (interval: 5s, timeout: 5s, retries: 5)
- Redis: `redis-cli ping` (interval: 5s, timeout: 5s, retries: 5)
- Backend: `curl -f http://localhost:8000/api/health` (interval: 30s, timeout: 10s, start-period: 60s, retries: 3)

---

## 7. 現在の完了状態と残課題

### 完了済み

- 全バックエンドファイルの実装（API, サービス, モデル, スキーマ, ワーカー, WebSocket）
- 全フロントエンドファイルの実装（ページ, コンポーネント, API通信, WebSocket, 型定義）
- Docker構成の実装（docker-compose.yml, Dockerfile x2, nginx.conf, redis.conf）
- 環境変数テンプレート（.env.example）
- Git除外設定（.gitignore）
- PC環境確認機能（CPU/RAM/GPU検出 + SystemInfoPanelコンポーネント）
- Whisperモデル選択機能（ドロップダウンUI + ジョブ別モデル指定 + 推奨設定自動検出）
- デバイス選択機能（CPU/GPU選択 + GPU自動検出 + ジョブ別デバイス指定）
- TranscriberServiceモデル再ロード対応（異なるモデル/デバイスへの動的切替）

### 残課題・将来の改善提案

#### 高優先度

| 課題 | 詳細 |
|------|------|
| Redis Pub/Sub -> WebSocket中継の実装 | Celeryワーカーがredis.publishした進捗メッセージを、FastAPI側でsubscribeしてWebSocket経由でクライアントに中継する処理が未実装。現状はフロントエンドのfetchJobポーリングに依存。 |
| テストコードの追加 | バックエンド: pytest + httpx (AsyncClient)。フロントエンド: Jest + React Testing Library。 |
| Alembicマイグレーション設定 | 現在は`create_tables()`による自動テーブル作成のみ。スキーマ変更時のマイグレーション管理が必要。 |

#### 中優先度

| 課題 | 詳細 |
|------|------|
| ユーザー認証機能（JWT） | python-jose は requirements.txt に含まれているが、認証エンドポイント・ミドルウェアは未実装。 |
| レート制限 | APIのレート制限（slowapi等）。特にアップロードとエクスポートのエンドポイント。 |
| Whisperモデルの事前ダウンロード最適化 | Dockerビルド時にモデルをダウンロードしているが、キャッシュ層の活用やモデルの外部ボリューム化で改善可能。 |
| 処理結果のキャッシュ機能 | 同一ファイルの再処理を避けるため、ファイルハッシュベースのキャッシュ機構。 |
| CI/CDパイプライン | GitHub Actions等によるテスト自動実行、Dockerイメージビルド、デプロイ自動化。 |

#### 低優先度

| 課題 | 詳細 |
|------|------|
| 話者分離機能（Speaker Diarization） | pyannote-audioやWhisperXとの連携で、話者ごとのテキスト分離を実現。 |
| 監視・ログ収集 | Prometheus + Grafanaによるメトリクス監視。ELK Stackによるログ集約。 |
| SSL/TLS設定 | 本番環境向けのHTTPS対応。Let's Encrypt + Nginx設定。 |
| ファイルのウイルススキャン | ClamAV等によるアップロードファイルのマルウェア検査。 |
| フロントエンドのJobList.tsxの型エラー | `PaginatedResponse<Job>`型が`types/index.ts`で定義されておらず、実際には`JobListResponse`を使うべき。`jobs.items`の参照も`jobs.jobs`にする必要がある。 |
| WebSocket URL不整合 | `websocket.ts`のURL構築 (`/ws/jobs/{jobId}/progress`) と`main.py`のルート (`/ws/{job_id}`) が不一致。フロントエンド側のURLをバックエンドに合わせる修正が必要。 |

---

## 8. 重要な技術的ポイント

### CeleryワーカーからWebSocket通知はRedis Pub/Subを経由

- CeleryワーカーとFastAPIサーバーは別プロセスで動作する。
- ワーカーから`redis.publish(f"job_progress:{job_id}", json_message)`で通知を発行。
- **現在の課題**: FastAPI側でRedis Pub/Subをsubscribeし、ConnectionManagerを通じてWebSocketクライアントに中継する仕組みが未実装。

### Whisperモデルのシングルトンパターンとスレッドセーフ性

- `TranscriberService`は`__new__`メソッドと`threading.Lock`でスレッドセーフなシングルトンを実装。
- GPU上のモデルは一度ロードされ、同じmodel+deviceの場合は再利用。異なる場合は自動的に再ロード。
- `_unload_model()`でモデル解放+`torch.cuda.empty_cache()`によるGPUメモリ解放を行う。
- Celeryの`worker_concurrency=1`により、同時に1つのタスクのみがWhisperモデルを使用するため、モデル再ロードが安全。
- ジョブごとに`whisper_model`/`whisper_device`を指定可能。未指定時はサーバーデフォルト設定にフォールバック。

### チャンクアップロードのバックエンド/フロントエンド間プロトコル

1. フロントエンドが`POST /api/upload/init`でジョブIDとchunk_sizeを取得。
2. ファイルをchunk_size単位でスライスし、`POST /api/upload/{id}/chunk`でFormData送信。
3. クエリパラメータで`chunk_index`と`total_chunks`を指定。
4. 全チャンク送信完了後、`POST /api/upload/{id}/complete`でチャンク結合をトリガー。

### 大容量ファイル処理時のメモリ管理

- チャンクアップロード: クライアント側は100MB単位でファイルをスライスし、メモリ消費を抑制。
- チャンク結合: サーバー側は1MB単位で読み書きし、全ファイルをメモリに載せない。
- Celeryワーカー: `worker_prefetch_multiplier=1`で1タスクずつ取得し、メモリ消費を制御。
- ディスク容量: `FileManager.check_disk_space()`で必要容量の2倍のマージンを確認。

### asyncpg -> psycopg2の同期セッション変換（Celeryワーカー用）

```python
# Celeryワーカーは同期的に動作するため、asyncpgではなくpsycopg2を使用
_sync_db_url = settings.DATABASE_URL.replace(
    "postgresql+asyncpg://", "postgresql+psycopg2://"
)
sync_engine = create_engine(_sync_db_url, pool_pre_ping=True)
SyncSessionFactory = sessionmaker(bind=sync_engine)
```

- FastAPI側: `postgresql+asyncpg://` + `AsyncSession`（非同期）
- Celeryワーカー側: `postgresql+psycopg2://` + `Session`（同期）
- 音声抽出サービスの非同期メソッドは`asyncio.new_event_loop()`で同期的に実行。

---

## 9. 開発環境での起動方法

### Docker Composeによる一括起動

```bash
# 全サービスのビルドと起動
docker compose up -d --build

# ログの確認
docker compose logs -f

# 特定サービスのログ確認
docker compose logs -f backend
docker compose logs -f worker
docker compose logs -f frontend

# サービスの停止
docker compose down

# ボリューム含めて完全削除
docker compose down -v
```

### ローカル開発（バックエンド単体）

```bash
cd backend

# 仮想環境の作成
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# 依存関係のインストール
pip install -r requirements.txt

# 環境変数の設定（ローカルのDB・Redisを使用する場合）
export DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/voice2character"
export REDIS_URL="redis://localhost:6379/0"

# FastAPI起動
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Celeryワーカー起動（別ターミナル）
celery -A app.workers.tasks worker --loglevel=info --concurrency=1
```

### ローカル開発（フロントエンド単体）

```bash
cd frontend

# 依存関係のインストール
npm install

# 開発サーバー起動
npm run dev
# -> http://localhost:3000

# ビルド
npm run build

# リント
npm run lint
```

---

## 10. AIアシスタントへの申し送り事項

### このプロジェクトを引き継ぐ場合に読むべきファイルの順序

1. **本ファイル（HANDOVER.md）** --- プロジェクト全体の概要と技術判断を把握する
2. **docker-compose.yml** --- サービス構成とインフラ全体像を理解する
3. **backend/app/config.py** --- 設定項目と環境変数の全体像を把握する
4. **backend/app/models/job.py** --- データモデル（Job, TranscriptionSegment）を理解する
5. **backend/app/schemas/job.py** --- APIのリクエスト/レスポンス型を把握する
6. **backend/app/main.py** --- FastAPIアプリの起動フローとミドルウェアを確認する
7. **backend/app/api/routes/upload.py** --- チャンクアップロードの仕組みを理解する
8. **backend/app/workers/tasks.py** --- 文字起こし処理パイプラインの全体フローを理解する
9. **backend/app/services/transcriber.py** --- Whisperの設定パラメータとモデル再ロード機構を確認する
10. **backend/app/services/system_info.py** --- Whisperモデルメタデータと推奨設定ロジックを確認する
11. **frontend/types/index.ts** --- フロントエンドの型定義を把握する
12. **frontend/lib/api.ts** --- API通信の実装を確認する
13. **frontend/lib/websocket.ts** --- WebSocket管理の実装を確認する
14. **frontend/components/FileUploader.tsx** --- チャンクアップロード・モデル/デバイス選択のフロントエンド実装を確認する
15. **frontend/components/SystemInfoPanel.tsx** --- システム環境情報パネルの実装を確認する
16. **frontend/app/jobs/[id]/page.tsx** --- ジョブ詳細ページのWebSocket連携を確認する

### 修正・追加機能を実装する際の注意事項

1. **コメントは日本語で統一すること** --- 既存コードのコメントは全て日本語で書かれている。新規コードも同様に日本語コメントで統一する。
2. **Pydanticスキーマとフロントエンド型定義の整合性** --- バックエンドのスキーマ（`schemas/job.py`）を変更した場合、フロントエンドの型定義（`types/index.ts`）も同期する必要がある。
3. **非同期/同期の使い分け** --- FastAPI側は`async/await`（asyncpg）、Celeryワーカー側は同期処理（psycopg2）。新しいサービスを追加する際はどちらのコンテキストで呼ばれるか注意する。
4. **Dockerのレイヤーキャッシュ** --- `requirements.txt`や`package.json`の変更は依存関係の再インストールを引き起こす。Dockerビルドが遅くなる点に注意。
5. **Whisperモデルのメモリ消費** --- large-v3モデルはGPU VRAM約10GB、CPU RAM約10GBを消費する。`worker_concurrency`を増やす場合はメモリ容量に注意。
6. **既知の不整合**:
   - `JobList.tsx`で`jobs.items`を参照しているが、バックエンドの`JobListResponse`のフィールドは`jobs`。
   - `websocket.ts`のWebSocket URLパス(`/ws/jobs/{jobId}/progress`)とバックエンドのルート(`/ws/{job_id}`)が不一致。
   - `types/index.ts`に`PaginatedResponse`型が未定義だが`JobList.tsx`で使用されている。
7. **環境変数の管理** --- `.env`ファイルはgitignoreに含まれている。新しい環境変数を追加した場合は`.env.example`にも追記すること。
8. **テストの追加** --- 現在テストコードは存在しない。機能追加時にはテストも併せて実装することを推奨。
9. **DBマイグレーション** --- 現在は`create_tables()`（`Base.metadata.create_all()`）による自動テーブル作成を使用。既存テーブルにカラムを追加した場合（例: `whisper_model`, `whisper_device`）、Docker環境を`docker compose down -v && docker compose up`で再構築するか、手動で`ALTER TABLE jobs ADD COLUMN ...`を実行する必要がある。
10. **Whisperモデル選択の仕様** --- `WHISPER_MODELS`定数（`system_info.py`）がモデルメタデータの唯一のソース。推奨エンジンは利用可能メモリの80%以内で動作する最大モデルを推奨する。ジョブのmodel/deviceがnullの場合はサーバーデフォルト（`config.py`のWHISPER_MODEL/WHISPER_DEVICE）にフォールバックする。
