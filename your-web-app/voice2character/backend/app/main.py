"""
FastAPIアプリケーションエントリーポイント

Voice2Characterバックエンドの起動設定を行う。
ミドルウェア、ルーター、ライフサイクルイベント、例外ハンドラーを定義する。
"""

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, WebSocket, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __app_name__, __version__
from app.api import api_router
from app.api.websocket import websocket_endpoint
from app.config import settings
from app.database import create_tables, dispose_engine
from app.services.redis_subscriber import redis_subscriber

# ---- ロギング設定 ----
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---- ライフサイクルイベント ----

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    アプリケーションのライフサイクル管理。

    起動時:
        - 必要なディレクトリの作成
        - データベーステーブルの作成

    終了時:
        - データベースエンジンの破棄
    """
    # ---- 起動処理 ----
    logger.info(
        "%s v%s を起動しています...",
        __app_name__,
        __version__,
    )

    # ディレクトリの自動作成
    settings.setup_directories()
    logger.info(
        "ディレクトリを初期化しました: upload=%s, processed=%s, temp=%s",
        settings.UPLOAD_DIR,
        settings.PROCESSED_DIR,
        settings.TEMP_DIR,
    )

    # データベーステーブルの作成
    try:
        await create_tables()
        logger.info("データベーステーブルを初期化しました。")
    except Exception as e:
        logger.error("データベース初期化エラー: %s", str(e))
        # DB接続失敗時もアプリは起動する（ヘルスチェックで検出可能）

    # Redis Pub/Subサブスクライバーの起動（進捗メッセージをWebSocketに中継）
    await redis_subscriber.start()

    logger.info(
        "%s v%s が起動しました。Whisperモデル: %s",
        __app_name__,
        __version__,
        settings.WHISPER_MODEL,
    )

    yield

    # ---- 終了処理 ----
    logger.info("%s を終了しています...", __app_name__)
    await redis_subscriber.stop()
    await dispose_engine()
    logger.info("データベース接続を解放しました。")


# ---- FastAPIアプリケーション ----

app = FastAPI(
    title=__app_name__,
    version=__version__,
    description=(
        "Voice2Character - 大容量MP4動画に対応した音声文字起こしWebアプリ。\n\n"
        "OpenAI Whisper Large-v3を使用し、高精度な日本語音声文字起こしを提供します。\n"
        "1000MB超の動画ファイルに対応するチャンクアップロード、\n"
        "リアルタイム進捗通知（WebSocket）、\n"
        "SRT/VTT/TXT/JSON/TSVの各種エクスポート形式に対応しています。"
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


# ---- ミドルウェア ----

# CORS（Cross-Origin Resource Sharing）設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],  # ファイルダウンロード用ヘッダーを公開
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """
    リクエストIDミドルウェア

    各リクエストにユニークなIDを付与し、レスポンスヘッダーとログに含める。
    トレーシングやデバッグに活用する。
    """
    request_id = str(uuid.uuid4())
    # リクエストのstateにIDを格納（下流のハンドラーから参照可能）
    request.state.request_id = request_id

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    """
    アクセスログミドルウェア

    各リクエストの処理時間、ステータスコード、パスをログに記録する。
    パフォーマンス監視とデバッグに活用する。
    """
    start_time = time.time()

    response = await call_next(request)

    # 処理時間の計算
    process_time_ms = (time.time() - start_time) * 1000

    # ヘルスチェックはDEBUGレベルでのみ記録（ログの肥大化防止）
    if request.url.path == "/api/health":
        logger.debug(
            "%s %s -> %d (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            process_time_ms,
        )
    else:
        logger.info(
            "%s %s -> %d (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            process_time_ms,
        )

    # レスポンスヘッダーに処理時間を追加
    response.headers["X-Process-Time-Ms"] = f"{process_time_ms:.1f}"
    return response


# ---- ルーター登録 ----

# APIルーターの登録
app.include_router(api_router)


# ---- WebSocketエンドポイント ----

@app.websocket("/ws/{job_id}")
async def ws_endpoint(websocket: WebSocket, job_id: str):
    """
    WebSocketエンドポイント

    ジョブの進捗をリアルタイムにクライアントへ通知する。
    """
    await websocket_endpoint(websocket, job_id)


# ---- ヘルスチェック ----

@app.get(
    "/api/health",
    tags=["ヘルスチェック"],
    summary="ヘルスチェック",
    description="アプリケーションの稼働状態を確認する。",
)
async def health_check() -> dict:
    """
    ヘルスチェックエンドポイント

    アプリケーション、データベース、Redisの稼働状態を返す。
    Dockerヘルスチェックやロードバランサーからの監視に使用する。
    """
    health = {
        "status": "healthy",
        "app": __app_name__,
        "version": __version__,
        "whisper_model": settings.WHISPER_MODEL,
    }

    # データベース接続チェック
    try:
        from app.database import engine
        async with engine.connect() as conn:
            await conn.execute(
                __import__("sqlalchemy").text("SELECT 1")
            )
        health["database"] = "connected"
    except Exception as e:
        health["database"] = f"disconnected: {str(e)}"
        health["status"] = "degraded"

    # Redis接続チェック
    try:
        import redis as redis_lib
        r = redis_lib.Redis.from_url(settings.REDIS_URL)
        r.ping()
        health["redis"] = "connected"
        r.close()
    except Exception as e:
        health["redis"] = f"disconnected: {str(e)}"
        health["status"] = "degraded"

    return health


# ---- グローバル例外ハンドラー ----

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    グローバル例外ハンドラー

    未処理の例外をキャッチし、統一されたエラーレスポンスを返す。
    本番環境ではスタックトレースを返さない。
    """
    request_id = getattr(request.state, "request_id", "unknown")

    logger.error(
        "未処理の例外: request_id=%s, path=%s, error=%s",
        request_id,
        request.url.path,
        str(exc),
        exc_info=True,
    )

    # 本番環境では詳細なエラー情報を隠蔽
    detail = str(exc) if settings.DEBUG else "サーバー内部エラーが発生しました。"

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": detail,
            "request_id": request_id,
        },
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc) -> JSONResponse:
    """404エラーハンドラー"""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "detail": "リクエストされたリソースが見つかりません。",
            "path": str(request.url.path),
        },
    )
