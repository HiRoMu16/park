"""
ジョブ関連のPydanticスキーマ

APIのリクエストボディ・レスポンスボディの型定義。
バリデーションルールもここで定義する。
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


# ---- 列挙型 ----

class JobStatus(str, Enum):
    """ジョブステータスの列挙型"""
    UPLOADING = "uploading"
    QUEUED = "queued"
    EXTRACTING = "extracting"
    TRANSCRIBING = "transcribing"
    COMPLETED = "completed"
    FAILED = "failed"


class ExportFormat(str, Enum):
    """エクスポート形式の列挙型"""
    TXT = "txt"
    SRT = "srt"
    VTT = "vtt"
    JSON = "json"
    TSV = "tsv"


# ---- リクエストスキーマ ----

class JobCreate(BaseModel):
    """
    ジョブ作成リクエスト

    アップロード初期化時にクライアントから送信される情報。
    """
    # 元のファイル名
    file_name: str = Field(..., min_length=1, max_length=512, description="アップロードするファイル名")
    # ファイルサイズ（バイト単位）
    file_size: int = Field(..., gt=0, description="ファイルサイズ（バイト）")
    # 文字起こし対象言語
    language: str = Field(default="ja", max_length=10, description="文字起こし対象の言語コード")

    @field_validator("file_name")
    @classmethod
    def validate_file_name(cls, v: str) -> str:
        """ファイル名に危険な文字が含まれていないか検証する"""
        # パストラバーサル攻撃の防止
        dangerous_chars = ["..", "/", "\\", "\x00"]
        for char in dangerous_chars:
            if char in v:
                raise ValueError(f"ファイル名に不正な文字が含まれています: {char!r}")
        return v


class UploadChunkRequest(BaseModel):
    """
    チャンクアップロードリクエスト

    大容量ファイルを分割してアップロードする際の各チャンクの情報。
    """
    # チャンクの通し番号（0始まり）
    chunk_index: int = Field(..., ge=0, description="チャンクのインデックス番号")
    # 全チャンク数
    total_chunks: int = Field(..., gt=0, description="全チャンク数")


class ExportRequest(BaseModel):
    """
    エクスポートリクエスト

    文字起こし結果をダウンロードする際の形式指定。
    """
    format: ExportFormat = Field(
        default=ExportFormat.TXT,
        description="エクスポート形式（txt, srt, vtt, json, tsv）",
    )


# ---- レスポンススキーマ ----

class SegmentResponse(BaseModel):
    """
    セグメントレスポンス

    文字起こし結果の1区間分の情報。
    """
    id: int = Field(..., description="セグメントID")
    segment_index: int = Field(..., description="セグメントの通し番号")
    start_time: float = Field(..., description="開始時間（秒）")
    end_time: float = Field(..., description="終了時間（秒）")
    text: str = Field(..., description="文字起こしテキスト")
    confidence: Optional[float] = Field(None, description="信頼度スコア（0.0～1.0）")

    model_config = {"from_attributes": True}


class JobResponse(BaseModel):
    """
    ジョブレスポンス

    ジョブの全情報を返すスキーマ。
    """
    id: str = Field(..., description="ジョブID（UUID）")
    file_name: str = Field(..., description="ファイル名")
    file_size: int = Field(..., description="ファイルサイズ（バイト）")
    duration: Optional[float] = Field(None, description="動画/音声の長さ（秒）")
    status: str = Field(..., description="ジョブステータス")
    progress: float = Field(..., description="進捗率（0.0～100.0）")
    error_message: Optional[str] = Field(None, description="エラーメッセージ")
    language: str = Field(..., description="文字起こし対象の言語")
    created_at: datetime = Field(..., description="作成日時")
    updated_at: datetime = Field(..., description="最終更新日時")
    completed_at: Optional[datetime] = Field(None, description="完了日時")

    model_config = {"from_attributes": True}


class JobListResponse(BaseModel):
    """
    ジョブ一覧レスポンス

    ページネーション情報付きのジョブ一覧。
    """
    jobs: List[JobResponse] = Field(..., description="ジョブ一覧")
    total: int = Field(..., description="全ジョブ数")
    page: int = Field(..., description="現在のページ番号")
    page_size: int = Field(..., description="1ページあたりのジョブ数")
    total_pages: int = Field(..., description="全ページ数")


class TranscriptionResponse(BaseModel):
    """
    文字起こし結果レスポンス

    ジョブ情報に全セグメントを付加したレスポンス。
    """
    job_id: str = Field(..., description="ジョブID")
    file_name: str = Field(..., description="ファイル名")
    duration: Optional[float] = Field(None, description="動画/音声の長さ（秒）")
    language: str = Field(..., description="文字起こし対象の言語")
    status: str = Field(..., description="ジョブステータス")
    segments: List[SegmentResponse] = Field(
        default_factory=list, description="文字起こしセグメント一覧"
    )
    full_text: str = Field(default="", description="全テキスト結合結果")


class UploadInitResponse(BaseModel):
    """
    アップロード初期化レスポンス

    チャンクアップロード開始時にクライアントに返す情報。
    """
    job_id: str = Field(..., description="作成されたジョブのID")
    upload_url: str = Field(..., description="チャンクアップロード先URL")
    chunk_size: int = Field(..., description="推奨チャンクサイズ（バイト）")


class ProgressUpdate(BaseModel):
    """
    進捗更新メッセージ（WebSocket用）

    WebSocket経由でクライアントに送信する進捗情報。
    """
    job_id: str = Field(..., description="ジョブID")
    status: str = Field(..., description="現在のステータス")
    progress: float = Field(..., description="進捗率（0.0～100.0）")
    message: str = Field(default="", description="ステータスメッセージ")
