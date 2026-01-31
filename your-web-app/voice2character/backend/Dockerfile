# ============================================================
# Voice2Character バックエンド Dockerfile
# マルチステージビルドによる最適化
# ============================================================

# ---- ステージ1: 依存関係のインストール ----
FROM python:3.11-slim AS builder

# システム依存パッケージのインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# 依存関係ファイルのコピーとインストール
COPY requirements.txt .
# PyTorch CPU版を使用（GPU版は約2GBでタイムアウトしやすい、CPU版は約200MB）
# GPU環境に切り替える場合は --extra-index-url 行を削除する
RUN pip install --no-cache-dir --prefix=/install --timeout=300 \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

# ---- ステージ2: Whisperモデルのプリダウンロード ----
FROM python:3.11-slim AS model-downloader

ARG WHISPER_MODEL=base

# ステージ1からPythonパッケージをコピー
COPY --from=builder /install /usr/local

# Whisperモデルを事前にダウンロード
RUN python -c "import whisper; whisper.load_model('${WHISPER_MODEL}', download_root='/models')"

# ---- ステージ3: 本番用イメージ ----
FROM python:3.11-slim AS production

# メタデータ
LABEL maintainer="Voice2Character Team"
LABEL description="Voice2Character バックエンド - 音声文字起こしサービス"

# 環境変数の設定
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WHISPER_MODEL_DIR=/models

# FFmpegおよび実行時に必要なシステムパッケージをインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 非rootユーザーの作成（セキュリティ対策）
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

# ステージ1からPythonパッケージをコピー
COPY --from=builder /install /usr/local

# ステージ2からWhisperモデルをコピー
COPY --from=model-downloader /models /models

# アプリケーションコードのコピー
COPY . .

# アップロード・処理済みディレクトリの作成と権限設定
# docker-compose.ymlの UPLOAD_DIR=/app/data/uploads, PROCESSED_DIR=/app/data/processed に合わせる
RUN mkdir -p /app/data/uploads /app/data/processed /app/tmp && \
    chown -R appuser:appuser /app /models

# 非rootユーザーに切り替え
USER appuser

# ポート公開
EXPOSE 8000

# ヘルスチェック設定
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# アプリケーション起動コマンド
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
