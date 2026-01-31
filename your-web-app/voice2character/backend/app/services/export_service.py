"""
エクスポートサービス

文字起こし結果を各種フォーマットに変換する。
対応形式: TXT, SRT, VTT, JSON, TSV
"""

import json
import logging
from typing import Any, List

from app.schemas.job import ExportFormat

logger = logging.getLogger(__name__)


def _format_time_srt(seconds: float) -> str:
    """
    秒数をSRT形式のタイムスタンプに変換する。

    SRT形式: HH:MM:SS,mmm（カンマ区切り）

    Args:
        seconds: 秒数

    Returns:
        str: SRT形式のタイムスタンプ文字列
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _format_time_vtt(seconds: float) -> str:
    """
    秒数をWebVTT形式のタイムスタンプに変換する。

    VTT形式: HH:MM:SS.mmm（ドット区切り）

    Args:
        seconds: 秒数

    Returns:
        str: WebVTT形式のタイムスタンプ文字列
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def _format_time_readable(seconds: float) -> str:
    """
    秒数を人間が読みやすい形式のタイムスタンプに変換する。

    形式: MM:SS（1時間以上の場合はH:MM:SS）

    Args:
        seconds: 秒数

    Returns:
        str: 読みやすいタイムスタンプ文字列
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class ExportService:
    """
    エクスポートサービス

    文字起こしセグメントを各種フォーマットの文字列に変換する。
    """

    def export(self, segments: List[Any], format: ExportFormat) -> str:
        """
        セグメントを指定フォーマットの文字列に変換する。

        Args:
            segments: TranscriptionSegmentオブジェクトのリスト
            format: エクスポート形式

        Returns:
            str: 変換された文字列

        Raises:
            ValueError: 未対応のフォーマットが指定された場合
        """
        format_handlers = {
            ExportFormat.TXT: self.export_txt,
            ExportFormat.SRT: self.export_srt,
            ExportFormat.VTT: self.export_vtt,
            ExportFormat.JSON: self.export_json,
            ExportFormat.TSV: self.export_tsv,
        }

        handler = format_handlers.get(format)
        if handler is None:
            raise ValueError(f"未対応のエクスポート形式: {format}")

        result = handler(segments)
        logger.info(
            "エクスポート完了: format=%s, segments=%d, length=%d",
            format.value,
            len(segments),
            len(result),
        )
        return result

    def export_txt(self, segments: List[Any]) -> str:
        """
        プレーンテキスト形式でエクスポートする。

        タイムスタンプ付きのテキストを出力する。

        Args:
            segments: セグメントオブジェクトのリスト

        Returns:
            str: プレーンテキスト文字列
        """
        lines = []

        for seg in segments:
            start = _format_time_readable(seg.start_time)
            end = _format_time_readable(seg.end_time)
            lines.append(f"[{start} - {end}] {seg.text}")

        return "\n".join(lines) + "\n"

    def export_srt(self, segments: List[Any]) -> str:
        """
        SRT字幕形式でエクスポートする。

        SubRip形式の字幕ファイルを生成する。
        形式:
            1
            00:00:00,000 --> 00:00:05,000
            テキスト

        Args:
            segments: セグメントオブジェクトのリスト

        Returns:
            str: SRT形式の文字列
        """
        blocks = []

        for idx, seg in enumerate(segments, start=1):
            start = _format_time_srt(seg.start_time)
            end = _format_time_srt(seg.end_time)
            block = f"{idx}\n{start} --> {end}\n{seg.text}"
            blocks.append(block)

        return "\n\n".join(blocks) + "\n"

    def export_vtt(self, segments: List[Any]) -> str:
        """
        WebVTT字幕形式でエクスポートする。

        Web Video Text Tracks形式の字幕ファイルを生成する。
        形式:
            WEBVTT

            00:00:00.000 --> 00:00:05.000
            テキスト

        Args:
            segments: セグメントオブジェクトのリスト

        Returns:
            str: WebVTT形式の文字列
        """
        lines = ["WEBVTT", ""]

        for seg in segments:
            start = _format_time_vtt(seg.start_time)
            end = _format_time_vtt(seg.end_time)
            lines.append(f"{start} --> {end}")
            lines.append(seg.text)
            lines.append("")

        return "\n".join(lines)

    def export_json(self, segments: List[Any]) -> str:
        """
        JSON形式でエクスポートする。

        タイムスタンプ、テキスト、信頼度を含むJSONを生成する。

        Args:
            segments: セグメントオブジェクトのリスト

        Returns:
            str: JSON形式の文字列
        """
        data = {
            "segments": [
                {
                    "index": seg.segment_index,
                    "start": seg.start_time,
                    "end": seg.end_time,
                    "text": seg.text,
                    "confidence": seg.confidence,
                }
                for seg in segments
            ],
            "full_text": "".join(seg.text for seg in segments),
        }

        return json.dumps(data, ensure_ascii=False, indent=2) + "\n"

    def export_tsv(self, segments: List[Any]) -> str:
        """
        TSV（タブ区切り）形式でエクスポートする。

        ヘッダー行付きのタブ区切りテキストを生成する。

        Args:
            segments: セグメントオブジェクトのリスト

        Returns:
            str: TSV形式の文字列
        """
        lines = ["index\tstart\tend\ttext\tconfidence"]

        for seg in segments:
            confidence_str = f"{seg.confidence:.4f}" if seg.confidence is not None else ""
            line = (
                f"{seg.segment_index}\t"
                f"{seg.start_time:.3f}\t"
                f"{seg.end_time:.3f}\t"
                f"{seg.text}\t"
                f"{confidence_str}"
            )
            lines.append(line)

        return "\n".join(lines) + "\n"
