"""
音声抽出サービス

FFmpegを使用して動画ファイルから音声をWAV形式で抽出する。
Whisperの入力に最適な形式（16kHz, モノラル, 16bit PCM）に変換する。
"""

import logging
from pathlib import Path

import ffmpeg

logger = logging.getLogger(__name__)


class AudioExtractor:
    """
    FFmpegベースの音声抽出サービス

    動画・音声ファイルからWhisper互換のWAV形式を生成する。
    """

    # Whisperが要求する音声フォーマット
    SAMPLE_RATE = 16000        # サンプリングレート: 16kHz
    CHANNELS = 1               # チャンネル数: モノラル
    AUDIO_CODEC = "pcm_s16le"  # コーデック: 16bit リトルエンディアンPCM

    async def extract_audio(
        self,
        input_path: str | Path,
        output_path: str | Path,
    ) -> Path:
        """
        動画/音声ファイルから音声をWAV(16kHz, mono)に変換する。

        Args:
            input_path: 入力ファイルパス（動画または音声）
            output_path: 出力WAVファイルパス

        Returns:
            Path: 出力ファイルのパス

        Raises:
            FileNotFoundError: 入力ファイルが存在しない場合
            RuntimeError: FFmpegの実行に失敗した場合
        """
        input_path = Path(input_path)
        output_path = Path(output_path)

        # 入力ファイルの存在確認
        if not input_path.exists():
            raise FileNotFoundError(f"入力ファイルが見つかりません: {input_path}")

        # 出力ディレクトリの作成
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(
            "音声抽出開始: input=%s, output=%s",
            input_path,
            output_path,
        )

        try:
            # FFmpegで音声を抽出・変換
            # -vn: 映像を無効化
            # -acodec pcm_s16le: 16bit PCM
            # -ar 16000: サンプリングレート16kHz
            # -ac 1: モノラル
            stream = (
                ffmpeg
                .input(str(input_path))
                .output(
                    str(output_path),
                    vn=None,              # 映像ストリームを除外
                    acodec=self.AUDIO_CODEC,
                    ar=self.SAMPLE_RATE,
                    ac=self.CHANNELS,
                )
                .overwrite_output()       # 既存ファイルを上書き
            )

            # FFmpegコマンドの実行
            stdout, stderr = stream.run(
                capture_stdout=True,
                capture_stderr=True,
            )

            # 出力ファイルの確認
            if not output_path.exists():
                raise RuntimeError("FFmpegの実行は完了しましたが、出力ファイルが生成されませんでした。")

            file_size = output_path.stat().st_size
            if file_size == 0:
                raise RuntimeError("生成された音声ファイルが空です。入力ファイルに音声トラックが含まれていない可能性があります。")

            logger.info(
                "音声抽出完了: output=%s, size=%d bytes",
                output_path,
                file_size,
            )

            return output_path

        except ffmpeg.Error as e:
            stderr_output = e.stderr.decode("utf-8", errors="replace") if e.stderr else "不明"
            error_msg = f"FFmpegエラー: {stderr_output}"
            logger.error("音声抽出失敗: %s", error_msg)
            raise RuntimeError(error_msg) from e

    async def get_duration(self, file_path: str | Path) -> float:
        """
        動画/音声ファイルの長さ（秒数）を取得する。

        Args:
            file_path: 対象ファイルのパス

        Returns:
            float: ファイルの長さ（秒単位）

        Raises:
            FileNotFoundError: ファイルが存在しない場合
            RuntimeError: 情報取得に失敗した場合
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"ファイルが見つかりません: {file_path}")

        try:
            # ffprobeでメタデータを取得
            probe = ffmpeg.probe(str(file_path))

            # duration情報の取得（formatセクションから）
            duration = float(probe.get("format", {}).get("duration", 0))

            if duration <= 0:
                # ストリームから取得を試みる
                for stream in probe.get("streams", []):
                    stream_duration = stream.get("duration")
                    if stream_duration:
                        duration = max(duration, float(stream_duration))

            logger.debug("ファイル長さ取得: file=%s, duration=%.2f秒", file_path, duration)
            return duration

        except ffmpeg.Error as e:
            stderr_output = e.stderr.decode("utf-8", errors="replace") if e.stderr else "不明"
            error_msg = f"ffprobeエラー: {stderr_output}"
            logger.error("ファイル長さ取得失敗: %s", error_msg)
            raise RuntimeError(error_msg) from e

    async def validate_media_file(self, file_path: str | Path) -> dict:
        """
        メディアファイルの妥当性を検証する。

        ファイルが有効な動画/音声ファイルであるか、
        音声トラックが含まれているかを確認する。

        Args:
            file_path: 検証対象のファイルパス

        Returns:
            dict: 検証結果（is_valid, has_audio, has_video, duration, format_name等）

        Raises:
            FileNotFoundError: ファイルが存在しない場合
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"ファイルが見つかりません: {file_path}")

        result = {
            "is_valid": False,
            "has_audio": False,
            "has_video": False,
            "duration": 0.0,
            "format_name": "",
            "error": None,
        }

        try:
            probe = ffmpeg.probe(str(file_path))

            # フォーマット情報
            format_info = probe.get("format", {})
            result["format_name"] = format_info.get("format_name", "")
            result["duration"] = float(format_info.get("duration", 0))

            # ストリーム情報の解析
            for stream in probe.get("streams", []):
                codec_type = stream.get("codec_type", "")
                if codec_type == "audio":
                    result["has_audio"] = True
                elif codec_type == "video":
                    result["has_video"] = True

            # 音声トラックがあれば有効とみなす
            result["is_valid"] = result["has_audio"]

            if not result["has_audio"]:
                result["error"] = "音声トラックが見つかりません。"

            logger.info(
                "メディアファイル検証: file=%s, valid=%s, audio=%s, video=%s",
                file_path,
                result["is_valid"],
                result["has_audio"],
                result["has_video"],
            )

        except ffmpeg.Error as e:
            stderr_output = e.stderr.decode("utf-8", errors="replace") if e.stderr else "不明"
            result["error"] = f"ファイル解析エラー: {stderr_output}"
            logger.error(
                "メディアファイル検証失敗: file=%s, error=%s",
                file_path,
                result["error"],
            )
        except Exception as e:
            result["error"] = f"予期しないエラー: {str(e)}"
            logger.error(
                "メディアファイル検証失敗: file=%s, error=%s",
                file_path,
                str(e),
            )

        return result
