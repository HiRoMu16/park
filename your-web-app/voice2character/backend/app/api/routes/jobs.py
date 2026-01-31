"""
ジョブ管理APIルート

文字起こしジョブの一覧取得、詳細表示、結果取得、削除を提供する。
"""

import logging
import math

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.job import Job, TranscriptionSegment
from app.schemas.job import (
    JobListResponse,
    JobResponse,
    SegmentResponse,
    TranscriptionResponse,
)
from app.services.file_manager import FileManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs")

# ファイル管理サービスのインスタンス
file_manager = FileManager()


@router.get(
    "",
    response_model=JobListResponse,
    summary="ジョブ一覧取得",
    description="文字起こしジョブの一覧をページネーション付きで取得する。",
)
async def list_jobs(
    page: int = Query(default=1, ge=1, description="ページ番号"),
    page_size: int = Query(default=20, ge=1, le=100, description="1ページあたりの件数"),
    db: AsyncSession = Depends(get_db),
) -> JobListResponse:
    """
    ジョブ一覧をページネーション付きで取得する。

    作成日時の降順でソートされる。
    """
    # 全件数の取得
    count_query = select(func.count(Job.id))
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # 全ページ数の計算
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    # ジョブ一覧の取得（作成日時の降順）
    offset = (page - 1) * page_size
    query = (
        select(Job)
        .order_by(Job.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(query)
    jobs = result.scalars().all()

    logger.debug("ジョブ一覧取得: page=%d, page_size=%d, total=%d", page, page_size, total)

    return JobListResponse(
        jobs=[JobResponse.model_validate(job) for job in jobs],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    summary="ジョブ詳細取得",
    description="指定されたジョブの詳細情報を取得する。",
)
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> JobResponse:
    """指定されたジョブIDのジョブ詳細を返す。"""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ジョブが見つかりません: {job_id}",
        )

    return JobResponse.model_validate(job)


@router.get(
    "/{job_id}/transcription",
    response_model=TranscriptionResponse,
    summary="文字起こし結果取得",
    description="指定されたジョブの文字起こし結果を全セグメント付きで取得する。",
)
async def get_transcription(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> TranscriptionResponse:
    """
    文字起こし結果を取得する。

    ジョブが完了状態の場合、全セグメント（タイムスタンプ付きテキスト）を返す。
    """
    # ジョブとセグメントを一括読み込み
    result = await db.execute(
        select(Job)
        .options(selectinload(Job.segments))
        .where(Job.id == job_id)
    )
    job = result.scalar_one_or_none()

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ジョブが見つかりません: {job_id}",
        )

    # セグメントをインデックス順にソート
    segments_sorted = sorted(job.segments, key=lambda s: s.segment_index)

    # 全テキストの結合
    full_text = "".join(seg.text for seg in segments_sorted)

    logger.debug(
        "文字起こし結果取得: job_id=%s, segments=%d",
        job_id,
        len(segments_sorted),
    )

    return TranscriptionResponse(
        job_id=job.id,
        file_name=job.file_name,
        duration=job.duration,
        language=job.language,
        status=job.status,
        segments=[SegmentResponse.model_validate(seg) for seg in segments_sorted],
        full_text=full_text,
    )


@router.delete(
    "/{job_id}",
    status_code=status.HTTP_200_OK,
    summary="ジョブ削除",
    description="指定されたジョブとその関連ファイルを削除する。",
)
async def delete_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    ジョブを削除する。

    1. 関連ファイル（アップロードファイル、一時ファイル）を削除
    2. DBレコード（ジョブ、セグメント）をカスケード削除
    """
    # ジョブの存在確認
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ジョブが見つかりません: {job_id}",
        )

    try:
        # 関連ファイルの削除
        await file_manager.cleanup_job_files(job_id)
    except Exception as e:
        # ファイル削除エラーはログに記録するが、DB削除は続行する
        logger.warning(
            "ジョブファイル削除中にエラー発生: job_id=%s, error=%s",
            job_id,
            str(e),
        )

    # DBレコードの削除（セグメントはカスケード削除）
    await db.delete(job)

    logger.info("ジョブ削除完了: job_id=%s", job_id)

    return {
        "status": "ok",
        "message": f"ジョブ {job_id} を削除しました。",
    }
