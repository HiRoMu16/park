"""
ExportServiceのユニットテスト

各エクスポート形式（TXT, SRT, VTT, JSON, TSV）の出力を検証する。
"""

import json
from dataclasses import dataclass
from typing import Optional

import pytest

from app.schemas.job import ExportFormat
from app.services.export_service import (
    ExportService,
    _format_time_readable,
    _format_time_srt,
    _format_time_vtt,
)


@dataclass
class MockSegment:
    """テスト用のセグメントモックオブジェクト"""
    segment_index: int
    start_time: float
    end_time: float
    text: str
    confidence: Optional[float] = None


@pytest.fixture
def export_service():
    return ExportService()


@pytest.fixture
def sample_segments():
    return [
        MockSegment(0, 0.0, 5.5, "こんにちは。", 0.95),
        MockSegment(1, 5.5, 12.3, "今日は天気がいいですね。", 0.88),
        MockSegment(2, 12.3, 18.0, "さようなら。", 0.92),
    ]


class TestFormatTimeSrt:
    """SRTタイムスタンプフォーマットのテスト"""

    def test_zero(self):
        assert _format_time_srt(0.0) == "00:00:00,000"

    def test_seconds_only(self):
        assert _format_time_srt(5.5) == "00:00:05,500"

    def test_minutes_and_seconds(self):
        assert _format_time_srt(125.75) == "00:02:05,750"

    def test_hours(self):
        assert _format_time_srt(3661.123) == "01:01:01,123"


class TestFormatTimeVtt:
    """VTTタイムスタンプフォーマットのテスト"""

    def test_zero(self):
        assert _format_time_vtt(0.0) == "00:00:00.000"

    def test_uses_dot_separator(self):
        """VTTはドット区切り（SRTはカンマ区切り）"""
        result = _format_time_vtt(5.5)
        assert "." in result
        assert "," not in result


class TestFormatTimeReadable:
    """人間可読タイムスタンプフォーマットのテスト"""

    def test_under_one_hour(self):
        assert _format_time_readable(125.0) == "02:05"

    def test_over_one_hour(self):
        assert _format_time_readable(3661.0) == "1:01:01"

    def test_zero(self):
        assert _format_time_readable(0.0) == "00:00"


class TestExportTxt:
    """TXTエクスポートのテスト"""

    def test_basic_output(self, export_service, sample_segments):
        result = export_service.export_txt(sample_segments)
        lines = result.strip().split("\n")
        assert len(lines) == 3
        assert "[00:00 - 00:05]" in lines[0]
        assert "こんにちは。" in lines[0]

    def test_empty_segments(self, export_service):
        result = export_service.export_txt([])
        assert result == "\n"


class TestExportSrt:
    """SRTエクスポートのテスト"""

    def test_basic_output(self, export_service, sample_segments):
        result = export_service.export_srt(sample_segments)
        blocks = result.strip().split("\n\n")
        assert len(blocks) == 3
        # 最初のブロックはインデックス1から始まる
        assert blocks[0].startswith("1\n")
        assert "-->" in blocks[0]
        assert "こんにちは。" in blocks[0]

    def test_srt_uses_comma_for_milliseconds(self, export_service, sample_segments):
        result = export_service.export_srt(sample_segments)
        # SRT形式はカンマで秒とミリ秒を区切る
        assert ",000 -->" in result or ",500 -->" in result


class TestExportVtt:
    """VTTエクスポートのテスト"""

    def test_starts_with_webvtt_header(self, export_service, sample_segments):
        result = export_service.export_vtt(sample_segments)
        assert result.startswith("WEBVTT")

    def test_uses_dot_for_milliseconds(self, export_service, sample_segments):
        result = export_service.export_vtt(sample_segments)
        lines = result.split("\n")
        # タイムスタンプ行にドット区切りが使われている
        timestamp_lines = [l for l in lines if "-->" in l]
        assert len(timestamp_lines) == 3
        for line in timestamp_lines:
            assert "." in line


class TestExportJson:
    """JSONエクスポートのテスト"""

    def test_valid_json(self, export_service, sample_segments):
        result = export_service.export_json(sample_segments)
        data = json.loads(result)
        assert "segments" in data
        assert "full_text" in data
        assert len(data["segments"]) == 3

    def test_segment_fields(self, export_service, sample_segments):
        result = export_service.export_json(sample_segments)
        data = json.loads(result)
        seg = data["segments"][0]
        assert "index" in seg
        assert "start" in seg
        assert "end" in seg
        assert "text" in seg
        assert "confidence" in seg

    def test_full_text(self, export_service, sample_segments):
        result = export_service.export_json(sample_segments)
        data = json.loads(result)
        expected = "こんにちは。今日は天気がいいですね。さようなら。"
        assert data["full_text"] == expected

    def test_japanese_not_escaped(self, export_service, sample_segments):
        """日本語がエスケープされず、そのまま出力される"""
        result = export_service.export_json(sample_segments)
        assert "こんにちは" in result


class TestExportTsv:
    """TSVエクスポートのテスト"""

    def test_has_header(self, export_service, sample_segments):
        result = export_service.export_tsv(sample_segments)
        first_line = result.split("\n")[0]
        assert "index" in first_line
        assert "start" in first_line
        assert "end" in first_line
        assert "text" in first_line
        assert "confidence" in first_line

    def test_tab_separated(self, export_service, sample_segments):
        result = export_service.export_tsv(sample_segments)
        lines = result.strip().split("\n")
        for line in lines:
            assert "\t" in line

    def test_data_rows_count(self, export_service, sample_segments):
        result = export_service.export_tsv(sample_segments)
        lines = result.strip().split("\n")
        # ヘッダー1行 + データ3行
        assert len(lines) == 4


class TestExportDispatch:
    """export() メソッドのディスパッチテスト"""

    def test_all_formats(self, export_service, sample_segments):
        """全エクスポート形式が正常に動作する"""
        for fmt in ExportFormat:
            result = export_service.export(sample_segments, fmt)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_invalid_format_raises(self, export_service, sample_segments):
        """無効なフォーマットでValueErrorが発生する"""
        with pytest.raises(ValueError, match="未対応"):
            export_service.export(sample_segments, "invalid")
