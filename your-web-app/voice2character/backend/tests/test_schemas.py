"""
Pydanticスキーマのバリデーションテスト

リクエスト/レスポンススキーマの入力検証を確認する。
"""

import pytest
from pydantic import ValidationError

from app.schemas.job import (
    ExportFormat,
    JobCreate,
    JobStatus,
    SegmentResponse,
    UploadInitResponse,
)


class TestJobCreate:
    """JobCreate スキーマのテスト"""

    def test_valid_minimal(self):
        """最小限のフィールドで作成可能"""
        job = JobCreate(file_name="test.mp4", file_size=1024)
        assert job.file_name == "test.mp4"
        assert job.file_size == 1024
        assert job.language == "ja"
        assert job.whisper_model is None
        assert job.whisper_device is None

    def test_valid_full(self):
        """全フィールド指定で作成可能"""
        job = JobCreate(
            file_name="video.mp4",
            file_size=1000000,
            language="en",
            whisper_model="large-v3",
            whisper_device="cuda",
        )
        assert job.whisper_model == "large-v3"
        assert job.whisper_device == "cuda"

    def test_empty_file_name_rejected(self):
        """空のファイル名は拒否される"""
        with pytest.raises(ValidationError):
            JobCreate(file_name="", file_size=1024)

    def test_zero_file_size_rejected(self):
        """ファイルサイズ0は拒否される"""
        with pytest.raises(ValidationError):
            JobCreate(file_name="test.mp4", file_size=0)

    def test_negative_file_size_rejected(self):
        """負のファイルサイズは拒否される"""
        with pytest.raises(ValidationError):
            JobCreate(file_name="test.mp4", file_size=-1)

    def test_path_traversal_rejected(self):
        """パストラバーサルを含むファイル名は拒否される"""
        with pytest.raises(ValidationError, match="不正な文字"):
            JobCreate(file_name="../etc/passwd", file_size=1024)

    def test_backslash_rejected(self):
        """バックスラッシュを含むファイル名は拒否される"""
        with pytest.raises(ValidationError, match="不正な文字"):
            JobCreate(file_name="test\\file.mp4", file_size=1024)

    def test_null_byte_rejected(self):
        """NULL文字を含むファイル名は拒否される"""
        with pytest.raises(ValidationError, match="不正な文字"):
            JobCreate(file_name="test\x00.mp4", file_size=1024)

    def test_invalid_whisper_model_rejected(self):
        """無効なモデル名は拒否される"""
        with pytest.raises(ValidationError, match="無効なモデル名"):
            JobCreate(
                file_name="test.mp4",
                file_size=1024,
                whisper_model="invalid-model",
            )

    def test_valid_whisper_models(self):
        """有効なモデル名一覧が受け入れられる"""
        for model in ["tiny", "base", "small", "medium", "large-v3"]:
            job = JobCreate(
                file_name="test.mp4",
                file_size=1024,
                whisper_model=model,
            )
            assert job.whisper_model == model

    def test_invalid_whisper_device_rejected(self):
        """無効なデバイス名は拒否される"""
        with pytest.raises(ValidationError, match="無効なデバイス"):
            JobCreate(
                file_name="test.mp4",
                file_size=1024,
                whisper_device="tpu",
            )

    def test_valid_whisper_devices(self):
        """有効なデバイス名一覧が受け入れられる"""
        for device in ["auto", "cpu", "cuda"]:
            job = JobCreate(
                file_name="test.mp4",
                file_size=1024,
                whisper_device=device,
            )
            assert job.whisper_device == device


class TestJobStatus:
    """JobStatus 列挙型のテスト"""

    def test_all_statuses(self):
        """全ステータス値が定義されている"""
        expected = {"uploading", "queued", "extracting", "transcribing", "completed", "failed"}
        actual = {s.value for s in JobStatus}
        assert actual == expected


class TestExportFormat:
    """ExportFormat 列挙型のテスト"""

    def test_all_formats(self):
        """全エクスポート形式が定義されている"""
        expected = {"txt", "srt", "vtt", "json", "tsv"}
        actual = {f.value for f in ExportFormat}
        assert actual == expected


class TestSegmentResponse:
    """SegmentResponse スキーマのテスト"""

    def test_valid(self):
        seg = SegmentResponse(
            id=1,
            segment_index=0,
            start_time=0.0,
            end_time=5.0,
            text="テスト",
            confidence=0.9,
        )
        assert seg.text == "テスト"

    def test_optional_confidence(self):
        """confidenceはNone可"""
        seg = SegmentResponse(
            id=1,
            segment_index=0,
            start_time=0.0,
            end_time=5.0,
            text="テスト",
        )
        assert seg.confidence is None
