"""
エクスポートAPIルート

文字起こし結果を各種フォーマットでダウンロードするエンドポイント。
対応形式: TXT, SRT, VTT, JSON, TSV
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.job import Job
from app.schemas.job import ExportFormat
from app.services.export_service import ExportService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/export")

# エクスポートサービスのインスタンス
export_service = ExportService()

# フォーマットごとのContent-TypeとMIMEタイプのマッピング
FORMAT_CONTENT_TYPES = {
    ExportFormat.TXT: "text/plain; charset=utf-8",
    ExportFormat.SRT: "application/x-subrip; charset=utf-8",
    ExportFormat.VTT: "text/vtt; charset=utf-8",
    ExportFormat.JSON: "application/json; charset=utf-8",
    ExportFormat.TSV: "text/tab-separated-values; charset=utf-8",
}

# フォーマットごとのファイル拡張子
FORMAT_EXTENSIONS = {
    ExportFormat.TXT: ".txt",
    ExportFormat.SRT: ".srt",
    ExportFormat.VTT: ".vtt",
    ExportFormat.JSON: ".json",
    ExportFormat.TSV: ".tsv",
}


@router.get(
    "/{job_id}",
    summary="文字起こし結果エクスポート",
    description="指定されたジョブの文字起こし結果を各種フォーマットでダウンロードする。",
)
async def export_transcription(
    job_id: str,
    format: ExportFormat = Query(
        default=ExportFormat.TXT,
        description="エクスポート形式（txt, srt, vtt, json, tsv）",
    ),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    文字起こし結果をファイルとしてダウンロードする。

    クエリパラメータのformatで出力形式を指定する。
    ファイルダウンロードレスポンスとして返却する。
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

    # 完了状態チェック
    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"文字起こしがまだ完了していません。ステータス: {job.status}",
        )

    # セグメントの有無チェック
    if not job.segments:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文字起こしセグメントが見つかりません。",
        )

    # セグメントをインデックス順にソート
    segments_sorted = sorted(job.segments, key=lambda s: s.segment_index)

    # フォーマットに応じたエクスポート処理
    try:
        content = export_service.export(segments_sorted, format)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"エクスポートエラー: {str(e)}",
        )

    # ダウンロードファイル名の生成
    base_name = job.file_name.rsplit(".", 1)[0] if "." in job.file_name else job.file_name
    extension = FORMAT_EXTENSIONS.get(format, ".txt")
    download_filename = f"{base_name}{extension}"

    content_type = FORMAT_CONTENT_TYPES.get(format, "text/plain; charset=utf-8")

    logger.info(
        "エクスポート実行: job_id=%s, format=%s, segments=%d",
        job_id,
        format.value,
        len(segments_sorted),
    )

    # StreamingResponseでファイルダウンロードを返す
    return StreamingResponse(
        content=iter([content.encode("utf-8")]),
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{download_filename}"',
            "Content-Length": str(len(content.encode("utf-8"))),
        },
    )
