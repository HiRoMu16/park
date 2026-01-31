"""
Celeryタスク定義

文字起こし処理のバックグラウンドタスク。
アップロード完了後にキューに投入され、以下の処理を順次実行する:
1. 音声抽出（FFmpeg）
2. 文字起こし（Whisper Large-v3）
3. 結果のDB保存
4. WebSocket経由の進捗通知
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models.job import Job, TranscriptionSegment
from app.services.audio_extractor import AudioExtractor
from app.services.file_manager import FileManager
from app.services.transcriber import TranscriberService
from app.workers import celery_app

logger = logging.getLogger(__name__)

# 同期用データベースエンジン（Celeryワーカーは同期的に動作するため）
# asyncpgをpsycopg2に変更
_sync_db_url = settings.DATABASE_URL.replace(
    "postgresql+asyncpg://", "postgresql+psycopg2://"
)
sync_engine = create_engine(_sync_db_url, pool_pre_ping=True)
SyncSessionFactory = sessionmaker(bind=sync_engine)

# サービスインスタンス
audio_extractor = AudioExtractor()
file_manager = FileManager()


def _get_sync_session() -> Session:
    """同期データベースセッションを取得する"""
    return SyncSessionFactory()


def _update_job_status(
    session: Session,
    job_id: str,
    status: str,
    progress: float,
    error_message: Optional[str] = None,
    duration: Optional[float] = None,
    completed: bool = False,
) -> None:
    """
    ジョブのステータスと進捗を更新する。

    Args:
        session: データベースセッション
        job_id: ジョブID
        status: 新しいステータス
        progress: 進捗率（0.0～100.0）
        error_message: エラーメッセージ（エラー時のみ）
        duration: 動画/音声の長さ（秒）
        completed: 完了フラグ
    """
    job = session.query(Job).filter(Job.id == job_id).first()
    if job is None:
        logger.error("ジョブが見つかりません: %s", job_id)
        return

    job.status = status
    job.progress = progress
    if error_message is not None:
        job.error_message = error_message
    if duration is not None:
        job.duration = duration
    if completed:
        job.completed_at = datetime.now(timezone.utc)

    session.commit()

    logger.info(
        "ジョブステータス更新: job_id=%s, status=%s, progress=%.1f%%",
        job_id,
        status,
        progress,
    )


def _send_progress_via_websocket(
    job_id: str,
    status: str,
    progress: float,
    message: str = "",
) -> None:
    """
    WebSocket経由で進捗更新を通知する。

    Celeryワーカーから直接WebSocketに送信できないため、
    Redis Pub/Subを経由して通知する。

    Args:
        job_id: ジョブID
        status: 現在のステータス
        progress: 進捗率
        message: ステータスメッセージ
    """
    try:
        import redis as redis_lib

        r = redis_lib.Redis.from_url(settings.REDIS_URL)
        import json

        update = {
            "job_id": job_id,
            "status": status,
            "progress": progress,
            "message": message,
        }
        # Redis Pub/Subチャンネルに発行
        r.publish(f"job_progress:{job_id}", json.dumps(update))
        r.close()
    except Exception as e:
        # WebSocket通知の失敗はタスク処理を止めない
        logger.warning(
            "WebSocket通知失敗: job_id=%s, error=%s",
            job_id,
            str(e),
        )


@celery_app.task(
    bind=True,
    name="process_transcription",
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def process_transcription_task(self, job_id: str) -> dict:
    """
    文字起こし処理タスク

    メインの処理パイプライン。以下のステップを順次実行する:
    1. ジョブステータスを「extracting」に更新
    2. FFmpegで音声抽出
    3. ジョブステータスを「transcribing」に更新
    4. Whisperで文字起こし（進捗コールバック付き）
    5. セグメントをDBに保存
    6. ステータスを「completed」に更新
    7. 進捗をWebSocket経由で通知

    Args:
        job_id: 処理対象のジョブID

    Returns:
        dict: 処理結果の概要

    Raises:
        Exception: リトライ上限を超えた場合にfailedステータスにする
    """
    session = _get_sync_session()
    logger.info("文字起こしタスク開始: job_id=%s", job_id)

    try:
        # ---- ステップ1: ジョブ情報の取得とステータス更新 ----
        job = session.query(Job).filter(Job.id == job_id).first()
        if job is None:
            raise ValueError(f"ジョブが見つかりません: {job_id}")

        file_path = job.file_path
        if not file_path:
            raise ValueError(f"ファイルパスが設定されていません: {job_id}")

        # ---- ステップ2: 音声抽出 ----
        _update_job_status(session, job_id, "extracting", 15.0)
        _send_progress_via_websocket(
            job_id, "extracting", 15.0, "動画から音声を抽出しています..."
        )

        # 動画/音声の長さを取得
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            duration = loop.run_until_complete(
                audio_extractor.get_duration(file_path)
            )
            _update_job_status(
                session, job_id, "extracting", 20.0, duration=duration
            )
        except Exception as e:
            logger.warning("動画長さ取得失敗: %s", str(e))
            duration = None

        # 音声をWAV形式で抽出
        audio_output_path = file_manager.get_file_path(job_id, "audio")
        loop.run_until_complete(
            audio_extractor.extract_audio(file_path, audio_output_path)
        )

        _update_job_status(session, job_id, "extracting", 30.0)
        _send_progress_via_websocket(
            job_id, "extracting", 30.0, "音声抽出が完了しました。"
        )

        # ---- ステップ3: 文字起こし ----
        _update_job_status(session, job_id, "transcribing", 35.0)
        _send_progress_via_websocket(
            job_id, "transcribing", 35.0, "文字起こしを開始します..."
        )

        # Whisperモデルのロード（初回のみ）
        transcriber = TranscriberService()
        if not transcriber.is_loaded:
            _send_progress_via_websocket(
                job_id, "transcribing", 35.0,
                "Whisperモデルをロードしています（初回のみ）..."
            )
            transcriber.load_model(
                model_name=settings.WHISPER_MODEL,
                device=settings.get_whisper_device(),
                download_root=settings.WHISPER_MODEL_DIR,
            )

        # 進捗コールバック関数
        # 文字起こしフェーズの進捗率は35%～90%
        def progress_callback(whisper_progress: float, message: str) -> None:
            """Whisperの進捗をジョブ進捗にマッピングする"""
            # whisper_progress: 0～100 -> job_progress: 35～90
            job_progress = 35.0 + (whisper_progress / 100.0) * 55.0
            _send_progress_via_websocket(
                job_id, "transcribing", job_progress, message
            )

        # 文字起こし実行
        segments = transcriber.transcribe(
            audio_path=str(audio_output_path),
            language=job.language,
            progress_callback=progress_callback,
        )

        _update_job_status(session, job_id, "transcribing", 90.0)
        _send_progress_via_websocket(
            job_id, "transcribing", 90.0, "文字起こし結果を保存しています..."
        )

        # ---- ステップ4: セグメントをDBに保存 ----
        for seg_data in segments:
            segment = TranscriptionSegment(
                job_id=job_id,
                segment_index=seg_data["segment_index"],
                start_time=seg_data["start_time"],
                end_time=seg_data["end_time"],
                text=seg_data["text"],
                confidence=seg_data.get("confidence"),
            )
            session.add(segment)

        session.commit()

        # ---- ステップ5: 完了処理 ----
        _update_job_status(
            session, job_id, "completed", 100.0, completed=True
        )
        _send_progress_via_websocket(
            job_id, "completed", 100.0,
            f"文字起こしが完了しました。{len(segments)}個のセグメントを検出しました。"
        )

        logger.info(
            "文字起こしタスク完了: job_id=%s, segments=%d",
            job_id,
            len(segments),
        )

        loop.close()

        return {
            "job_id": job_id,
            "status": "completed",
            "segments_count": len(segments),
            "duration": duration,
        }

    except Exception as e:
        error_msg = f"文字起こしタスクエラー: {str(e)}"
        logger.error(error_msg, exc_info=True)

        # ジョブステータスをfailedに更新
        try:
            _update_job_status(
                session, job_id, "failed", 0.0, error_message=str(e)
            )
            _send_progress_via_websocket(
                job_id, "failed", 0.0, f"エラーが発生しました: {str(e)}"
            )
        except Exception as update_error:
            logger.error(
                "ステータス更新失敗: job_id=%s, error=%s",
                job_id,
                str(update_error),
            )

        # リトライ可能な場合はリトライ
        if self.request.retries < self.max_retries:
            logger.info(
                "タスクリトライ: job_id=%s, retry=%d/%d",
                job_id,
                self.request.retries + 1,
                self.max_retries,
            )
            raise self.retry(exc=e)

        return {
            "job_id": job_id,
            "status": "failed",
            "error": str(e),
        }

    finally:
        session.close()
