"""
Whisper文字起こしサービス

OpenAI Whisper Large-v3を使用した高精度日本語音声文字起こし。
GPU/CPU自動検出、進捗コールバック、メモリ効率的な処理を提供する。
"""

import logging
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class TranscriberService:
    """
    Whisper文字起こしサービス（シングルトン）

    モデルを一度だけロードし、複数のリクエストで再利用する。
    スレッドセーフなシングルトンパターンを採用。
    """

    _instance: Optional["TranscriberService"] = None
    _lock = threading.Lock()
    _model = None
    _model_loaded = False

    def __new__(cls) -> "TranscriberService":
        """シングルトンパターン: インスタンスが未作成なら新規作成"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def __init__(self) -> None:
        """初期化（シングルトンのため2回目以降はスキップ）"""
        # 既に初期化済みなら何もしない
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._device: str = "cpu"
        self._current_model_name: str | None = None
        self._current_device: str | None = None

    def load_model(
        self,
        model_name: str = "large-v3",
        device: str = "auto",
        download_root: str | None = None,
    ) -> None:
        """
        Whisperモデルをロードする。

        同じモデル・デバイスが既にロード済みの場合はスキップする。
        異なるモデル・デバイスが指定された場合は既存モデルを解放してから再ロードする。

        Args:
            model_name: 使用するモデル名（例: "large-v3"）
            device: 推論デバイス（"auto", "cuda", "cpu"）
            download_root: モデルダウンロード先ディレクトリ
        """
        import torch
        import whisper

        # デバイスの解決（"auto"の場合はCUDA検出）
        resolved_device = device
        if device == "auto":
            resolved_device = "cuda" if torch.cuda.is_available() else "cpu"

        # 同じモデル・デバイスなら再ロード不要
        if (
            self._model_loaded
            and self._current_model_name == model_name
            and self._current_device == resolved_device
        ):
            logger.info(
                "Whisperモデルは既にロード済みです: model=%s, device=%s",
                model_name,
                resolved_device,
            )
            return

        # 異なるモデル/デバイスが要求された場合、既存モデルを解放
        if self._model_loaded:
            logger.info(
                "モデル変更を検出。既存モデルを解放します: %s(%s) -> %s(%s)",
                self._current_model_name,
                self._current_device,
                model_name,
                resolved_device,
            )
            self._unload_model()

        self._device = resolved_device

        logger.info(
            "Whisperモデルロード開始: model=%s, device=%s",
            model_name,
            self._device,
        )

        # モデルのロード
        self._model = whisper.load_model(
            model_name,
            device=self._device,
            download_root=download_root,
        )

        self._model_loaded = True
        self._current_model_name = model_name
        self._current_device = self._device

        logger.info(
            "Whisperモデルロード完了: model=%s, device=%s",
            model_name,
            self._device,
        )

    def _unload_model(self) -> None:
        """
        現在のモデルをメモリから解放する。

        GPUメモリも明示的に解放する。
        """
        if self._model is not None:
            del self._model
            self._model = None
            self._model_loaded = False
            self._current_model_name = None
            self._current_device = None

            # GPUメモリの解放
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass

            logger.info("Whisperモデルをメモリから解放しました。")

    def transcribe(
        self,
        audio_path: str | Path,
        language: str = "ja",
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> List[Dict[str, Any]]:
        """
        音声ファイルを文字起こしする。

        Whisper Large-v3を使用し、日本語に最適化したパラメータで処理する。
        進捗コールバックを通じて処理の進捗を通知できる。

        Args:
            audio_path: 入力音声ファイルパス（WAV形式推奨）
            language: 文字起こし対象の言語コード
            progress_callback: 進捗通知用コールバック関数 (progress: float, message: str) -> None

        Returns:
            List[Dict]: セグメント情報のリスト。各セグメントは以下のキーを持つ:
                - segment_index (int): セグメント番号
                - start_time (float): 開始時間（秒）
                - end_time (float): 終了時間（秒）
                - text (str): 文字起こしテキスト
                - confidence (float): 信頼度スコア

        Raises:
            RuntimeError: モデル未ロードまたは文字起こし失敗時
            FileNotFoundError: 音声ファイルが存在しない場合
        """
        if not self._model_loaded or self._model is None:
            raise RuntimeError(
                "Whisperモデルがロードされていません。load_model()を先に呼び出してください。"
            )

        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"音声ファイルが見つかりません: {audio_path}")

        logger.info(
            "文字起こし開始: audio=%s, language=%s",
            audio_path,
            language,
        )

        if progress_callback:
            progress_callback(0.0, "文字起こしを開始しています...")

        try:
            # 日本語に最適化したWhisperパラメータ
            transcribe_options = {
                "language": language,
                "task": "transcribe",
                "beam_size": 5,         # ビームサーチ幅（精度重視）
                "best_of": 5,           # 候補生成数（精度重視）
                "temperature": 0,       # 決定的生成（temperature=0が最も安定）
                "initial_prompt": "以下は日本語の音声の書き起こしです。",
                "condition_on_previous_text": True,  # 前のテキストを条件に含める
                "verbose": False,       # 詳細ログは無効
                "fp16": self._device == "cuda",  # GPU使用時はFP16で高速化
            }

            if progress_callback:
                progress_callback(5.0, "Whisperモデルで音声を解析中...")

            # 文字起こし実行
            result = self._model.transcribe(
                str(audio_path),
                **transcribe_options,
            )

            if progress_callback:
                progress_callback(80.0, "セグメント情報を処理中...")

            # セグメント情報の整形
            segments = self._process_segments(result.get("segments", []))

            if progress_callback:
                progress_callback(100.0, "文字起こし完了")

            logger.info(
                "文字起こし完了: audio=%s, segments=%d",
                audio_path,
                len(segments),
            )

            return segments

        except Exception as e:
            error_msg = f"文字起こしエラー: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg) from e

    def _process_segments(
        self,
        raw_segments: list,
    ) -> List[Dict[str, Any]]:
        """
        Whisperの出力セグメントを整形する。

        生のWhisper出力からアプリケーションで使用する形式に変換する。

        Args:
            raw_segments: Whisperが出力した生セグメントリスト

        Returns:
            List[Dict]: 整形されたセグメント情報のリスト
        """
        processed = []

        for idx, segment in enumerate(raw_segments):
            # 信頼度の計算（各トークンのno_speech_probの反転平均）
            # Whisperはno_speech_probを出力するため、1から引いて信頼度とする
            confidence = None
            if "no_speech_prob" in segment:
                confidence = round(1.0 - segment["no_speech_prob"], 4)

            processed.append({
                "segment_index": idx,
                "start_time": round(segment.get("start", 0.0), 3),
                "end_time": round(segment.get("end", 0.0), 3),
                "text": segment.get("text", "").strip(),
                "confidence": confidence,
            })

        # 空テキストのセグメントを除外
        processed = [seg for seg in processed if seg["text"]]

        # セグメントインデックスの再採番
        for idx, seg in enumerate(processed):
            seg["segment_index"] = idx

        return processed

    @property
    def is_loaded(self) -> bool:
        """モデルがロード済みかどうか"""
        return self._model_loaded

    @property
    def device(self) -> str:
        """現在の推論デバイス"""
        return self._device

    @property
    def current_model_name(self) -> str | None:
        """現在ロード中のモデル名"""
        return self._current_model_name

    @property
    def current_device(self) -> str | None:
        """現在の推論デバイス名"""
        return self._current_device
