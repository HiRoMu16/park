"""
アップロードAPIルート

チャンクアップロードに対応した大容量ファイルアップロードエンドポイント。
1000MB超のMP4動画に対応するため、ファイルを分割してアップロードする。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.job import Job
from app.schemas.job import (
    JobCreate,
    JobResponse,
    UploadChunkRequest,
    UploadInitResponse,
)
from app.services.file_manager import FileManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload")

# ファイル管理サービスのインスタンス
file_manager = FileManager()


@router.post(
    "/init",
    response_model=UploadInitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="アップロード初期化",
    description="チャンクアップロードを開始するためのジョブを作成する。",
)
async def init_upload(
    request: JobCreate,
    db: AsyncSession = Depends(get_db),
) -> UploadInitResponse:
    """
    アップロードを初期化してジョブを作成する。

    1. ファイル拡張子のバリデーション
    2. ファイルサイズのバリデーション
    3. Jobレコードの作成
    4. job_idとアップロードURLを返却
    """
    # ファイル拡張子チェック
    if not settings.is_allowed_extension(request.file_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"許可されていないファイル形式です。対応形式: {', '.join(settings.ALLOWED_EXTENSIONS)}",
        )

    # ファイルサイズチェック
    if request.file_size > settings.MAX_FILE_SIZE:
        max_size_gb = settings.MAX_FILE_SIZE / (1024 ** 3)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"ファイルサイズが上限（{max_size_gb:.1f}GB）を超えています。",
        )

    # ジョブの作成
    job = Job(
        file_name=request.file_name,
        file_size=request.file_size,
        language=request.language,
        status="uploading",
        progress=0.0,
    )
    db.add(job)
    await db.flush()  # IDを確定させる
    await db.refresh(job)

    logger.info(
        "アップロード初期化完了: job_id=%s, file_name=%s, file_size=%d",
        job.id,
        job.file_name,
        job.file_size,
    )

    return UploadInitResponse(
        job_id=job.id,
        upload_url=f"/api/upload/{job.id}/chunk",
        chunk_size=settings.CHUNK_SIZE,
    )


@router.post(
    "/{job_id}/chunk",
    status_code=status.HTTP_200_OK,
    summary="チャンクアップロード",
    description="ファイルの一部（チャンク）をアップロードする。",
)
async def upload_chunk(
    job_id: str,
    chunk_index: int,
    total_chunks: int,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    ファイルチャンクをアップロードする。

    各チャンクは一時ディレクトリに保存される。
    全チャンクがアップロードされた後、completeエンドポイントで結合する。
    """
    # ジョブの存在確認
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ジョブが見つかりません: {job_id}",
        )

    # ステータスチェック（アップロード中のみチャンク受付可能）
    if job.status != "uploading":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"このジョブは現在アップロードを受け付けていません。ステータス: {job.status}",
        )

    # チャンクインデックスのバリデーション
    if chunk_index < 0 or chunk_index >= total_chunks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"無効なチャンクインデックスです: {chunk_index} (全チャンク数: {total_chunks})",
        )

    # チャンクデータの読み取りと保存
    chunk_data = await file.read()
    await file_manager.save_chunk(job_id, chunk_index, chunk_data)

    # 進捗率の更新（アップロードフェーズは0～10%）
    upload_progress = ((chunk_index + 1) / total_chunks) * 10.0
    job.progress = min(upload_progress, 10.0)

    logger.info(
        "チャンクアップロード完了: job_id=%s, chunk=%d/%d",
        job_id,
        chunk_index + 1,
        total_chunks,
    )

    return {
        "status": "ok",
        "chunk_index": chunk_index,
        "total_chunks": total_chunks,
        "message": f"チャンク {chunk_index + 1}/{total_chunks} をアップロードしました。",
    }


@router.post(
    "/{job_id}/complete",
    response_model=JobResponse,
    status_code=status.HTTP_200_OK,
    summary="アップロード完了",
    description="全チャンクを結合し、文字起こし処理をキューに投入する。",
)
async def complete_upload(
    job_id: str,
    total_chunks: int,
    db: AsyncSession = Depends(get_db),
) -> JobResponse:
    """
    アップロードを完了する。

    1. 全チャンクを結合して1つのファイルにする
    2. 一時チャンクファイルを削除
    3. Celeryタスクをキューに投入
    4. ジョブステータスを「queued」に更新
    """
    # ジョブの存在確認
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ジョブが見つかりません: {job_id}",
        )

    # ステータスチェック
    if job.status != "uploading":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"このジョブは現在アップロード完了を受け付けていません。ステータス: {job.status}",
        )

    try:
        # チャンクの結合
        merged_path = await file_manager.merge_chunks(
            job_id, total_chunks, job.file_name
        )

        # チャンク一時ファイルの削除
        await file_manager.cleanup_chunks(job_id)

        # ジョブ情報の更新
        job.file_path = str(merged_path)
        job.status = "queued"
        job.progress = 10.0

        # Celeryタスクの投入
        from app.workers.tasks import process_transcription_task
        process_transcription_task.delay(job_id)

        logger.info(
            "アップロード完了・タスク投入: job_id=%s, file_path=%s",
            job_id,
            merged_path,
        )

    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"チャンクファイルが不足しています: {e}",
        )
    except Exception as e:
        # エラー発生時はジョブをfailedに更新
        job.status = "failed"
        job.error_message = f"アップロード完了処理でエラーが発生しました: {str(e)}"
        logger.error(
            "アップロード完了エラー: job_id=%s, error=%s",
            job_id,
            str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"アップロード完了処理でエラーが発生しました: {str(e)}",
        )

    return JobResponse.model_validate(job)
