"""
Whisper文字起こしサービス

OpenAI Whisper Large-v3を使用した高精度日本語音声文字起こし。
GPU/CPU自動検出、進捗コールバック、メモリ効率的な処理を提供する。
"""

import logging
import threading
import time
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

    # モデル別の推定処理速度（リアルタイム倍率: 音声1秒あたり何秒で処理するか）
    # 値が小さいほど高速。例: 0.2 = 音声1秒を0.2秒で処理（5倍速）
    _SPEED_FACTORS: Dict[str, Dict[str, float]] = {
        "tiny":     {"cpu": 0.15,  "cuda": 0.03},
        "base":     {"cpu": 0.25,  "cuda": 0.05},
        "small":    {"cpu": 0.5,   "cuda": 0.08},
        "medium":   {"cpu": 1.2,   "cuda": 0.12},
        "large-v3": {"cpu": 2.5,   "cuda": 0.18},
    }

    def _estimate_processing_seconds(self, audio_duration: float) -> float:
        """
        音声の長さとモデル/デバイスから推定処理時間を算出する。

        Args:
            audio_duration: 音声の長さ（秒）

        Returns:
            float: 推定処理時間（秒）
        """
        model_name = self._current_model_name or "base"
        device = self._current_device or "cpu"
        device_key = "cuda" if "cuda" in device else "cpu"
        model_factors = self._SPEED_FACTORS.get(model_name, self._SPEED_FACTORS["base"])
        factor = model_factors.get(device_key, model_factors["cpu"])
        # 安全マージン1.2倍（実際より少し長めに見積もる）
        return audio_duration * factor * 1.2

    def transcribe(
        self,
        audio_path: str | Path,
        language: str = "ja",
        progress_callback: Optional[Callable[[float, str], None]] = None,
        audio_duration: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        音声ファイルを文字起こしする。

        Whisper Large-v3を使用し、日本語に最適化したパラメータで処理する。
        進捗コールバックを通じて処理の進捗を通知できる。
        audio_durationが指定された場合、推定処理時間に基づく
        タイマーベースの進捗通知を行う。

        Args:
            audio_path: 入力音声ファイルパス（WAV形式推奨）
            language: 文字起こし対象の言語コード
            progress_callback: 進捗通知用コールバック関数 (progress: float, message: str) -> None
            audio_duration: 音声の長さ（秒）。指定時にタイマーベース進捗推定を使用

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
            "文字起こし開始: audio=%s, language=%s, duration=%s",
            audio_path,
            language,
            audio_duration,
        )

        if progress_callback:
            progress_callback(0.0, "文字起こしを開始しています...")

        try:
            # "auto"の場合はNoneに変換（Whisperの自動言語検出を使用）
            effective_language = None if language == "auto" else language

            # 日本語に最適化したWhisperパラメータ（ハルシネーション対策済み）
            transcribe_options = {
                "language": effective_language,
                "task": "transcribe",
                "beam_size": 5,         # ビームサーチ幅（精度重視）
                "best_of": 5,           # 候補生成数（精度重視）
                # タプルで指定することで温度フォールバック機構を有効化:
                # 品質閾値を下回った場合、自動的に次のtemperatureで再試行する
                "temperature": (0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
                "initial_prompt": "以下は日本語の音声の書き起こしです。" if effective_language == "ja" else None,
                # ハルシネーション対策: 前セグメントのテキストを条件に含めない
                # Trueの場合、一度ハルシネーションが発生すると連鎖的に伝播する
                "condition_on_previous_text": False,
                "verbose": False,       # 詳細ログは無効
                "fp16": self._device == "cuda",  # GPU使用時はFP16で高速化
                # 品質フィルタリング閾値（温度フォールバックのトリガー条件）
                "compression_ratio_threshold": 2.4,  # gzip圧縮比がこの値を超えたら再試行
                "logprob_threshold": -1.0,           # 平均log確率がこの値未満なら再試行
                "no_speech_threshold": 0.6,          # 無音確率がこの値を超えたら無音セグメント
            }

            # --- タイマーベース進捗推定スレッドの起動 ---
            stop_event = threading.Event()
            estimated_total = None

            if progress_callback and audio_duration and audio_duration > 0:
                estimated_total = self._estimate_processing_seconds(audio_duration)
                start_time = time.monotonic()

                def _progress_reporter() -> None:
                    """定期的に推定進捗とETAを通知するバックグラウンドスレッド"""
                    while not stop_event.wait(timeout=2.0):
                        elapsed = time.monotonic() - start_time
                        # 推定進捗: 0%〜95%の範囲（100%には到達させない）
                        ratio = min(elapsed / estimated_total, 0.95) if estimated_total > 0 else 0
                        estimated_progress = ratio * 100.0
                        eta = max(0.0, estimated_total - elapsed)
                        # ETA情報をメッセージに埋め込む（JSON解析用にプレフィックス付与）
                        if eta >= 60:
                            eta_text = f"残り約{int(eta // 60)}分{int(eta % 60)}秒"
                        else:
                            eta_text = f"残り約{int(eta)}秒"
                        progress_callback(
                            estimated_progress,
                            f"ETA:{eta:.0f}|文字起こし中... {eta_text}",
                        )

                reporter = threading.Thread(target=_progress_reporter, daemon=True)
                reporter.start()
                logger.info(
                    "進捗推定スレッド起動: estimated_total=%.1fs, audio_duration=%.1fs",
                    estimated_total, audio_duration,
                )
            else:
                if progress_callback:
                    progress_callback(5.0, "Whisperモデルで音声を解析中...")

            # 文字起こし実行（ブロッキング呼び出し）
            result = self._model.transcribe(
                str(audio_path),
                **transcribe_options,
            )

            # 進捗推定スレッドの停止
            stop_event.set()

            if progress_callback:
                progress_callback(95.0, "セグメント情報を処理中...")

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
            stop_event.set()
            error_msg = f"文字起こしエラー: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg) from e

    # 連続類似セグメントの検出用カウンター閾値
    _MAX_CONSECUTIVE_SIMILAR = 3

    def _process_segments(
        self,
        raw_segments: list,
    ) -> List[Dict[str, Any]]:
        """
        Whisperの出力セグメントを整形し、ハルシネーションを検出・除外する。

        生のWhisper出力からアプリケーションで使用する形式に変換する。
        以下のハルシネーション検出ロジックを適用する:
        - 無音確率が高いセグメントの除外
        - テキスト内の異常な繰り返しパターンの検出・除外（任意位置検出対応）
        - 連続する同一・類似テキストの検出・除外
        - 連続類似セグメント蓄積の打ち切り

        Args:
            raw_segments: Whisperが出力した生セグメントリスト

        Returns:
            List[Dict]: 整形・フィルタリングされたセグメント情報のリスト
        """
        processed = []
        # 連続類似セグメントのカウンター
        consecutive_similar_count = 0
        last_core_phrase: str | None = None

        for idx, segment in enumerate(raw_segments):
            text = segment.get("text", "").strip()

            # 空テキストのセグメントをスキップ
            if not text:
                continue

            # 信頼度の計算（no_speech_probの反転）
            no_speech_prob = segment.get("no_speech_prob", 0.0)
            confidence = round(1.0 - no_speech_prob, 4) if no_speech_prob is not None else None

            # --- ハルシネーション検出 ---

            # 検出1: 無音確率が高すぎるセグメントを除外
            if no_speech_prob is not None and no_speech_prob > 0.8:
                logger.debug(
                    "ハルシネーション疑い（高無音確率）: segment=%d, "
                    "no_speech_prob=%.3f, text='%s'",
                    idx, no_speech_prob, text[:50],
                )
                continue

            # 検出2: テキスト内部の繰り返しパターンを検出（任意位置対応）
            if self._is_repetitive_text(text):
                logger.warning(
                    "ハルシネーション検出（繰り返しパターン）: segment=%d, text='%s'",
                    idx, text[:80],
                )
                continue

            # 検出3: 直前のセグメントと同一テキストの連続を検出
            if processed and processed[-1]["text"] == text:
                logger.debug(
                    "ハルシネーション検出（連続同一テキスト）: segment=%d, text='%s'",
                    idx, text[:50],
                )
                continue

            # 検出4: セグメントの主要フレーズが連続して類似しているか検出
            core = self._extract_core_phrase(text)
            if core and core == last_core_phrase:
                consecutive_similar_count += 1
            else:
                consecutive_similar_count = 0
                last_core_phrase = core

            if consecutive_similar_count >= self._MAX_CONSECUTIVE_SIMILAR:
                logger.warning(
                    "ハルシネーション検出（連続類似セグメント %d回目）: "
                    "segment=%d, text='%s'",
                    consecutive_similar_count + 1, idx, text[:80],
                )
                continue

            processed.append({
                "segment_index": idx,
                "start_time": round(segment.get("start", 0.0), 3),
                "end_time": round(segment.get("end", 0.0), 3),
                "text": text,
                "confidence": confidence,
            })

        # セグメントインデックスの再採番
        for idx, seg in enumerate(processed):
            seg["segment_index"] = idx

        # フィルタリング結果のログ出力
        original_count = len(raw_segments)
        filtered_count = original_count - len(processed)
        if filtered_count > 0:
            logger.info(
                "ハルシネーションフィルタリング: 元セグメント=%d, "
                "除外=%d, 残存=%d",
                original_count, filtered_count, len(processed),
            )

        return processed

    @staticmethod
    def _extract_core_phrase(text: str, max_len: int = 30) -> str | None:
        """
        テキストから主要フレーズを抽出する。

        句点「。」で分割し、最も長いフレーズを返す。
        連続類似セグメントの検出に使用する。

        Args:
            text: 対象テキスト
            max_len: 主要フレーズの最大長（超過時は先頭を使用）

        Returns:
            str | None: 主要フレーズ。抽出できない場合はNone
        """
        if not text:
            return None
        # 句点で分割し、空でない最も長いフレーズを取得
        phrases = [p.strip() for p in text.replace("！", "。").replace("？", "。").split("。") if p.strip()]
        if not phrases:
            return text[:max_len] if len(text) > max_len else text
        longest = max(phrases, key=len)
        return longest[:max_len]

    @staticmethod
    def _is_repetitive_text(
        text: str,
        min_pattern_len: int = 3,
        max_pattern_len: int = 50,
    ) -> bool:
        """
        テキストが繰り返しパターンで構成されているかを検出する。

        テキスト内の任意の位置からパターンを抽出し、
        そのパターンがテキストの大部分を占めているかを検査する。

        検出方式:
        1. 先頭起点パターン: テキスト先頭からのパターンで全体の60%以上かつ3回以上
        2. 任意位置パターン: テキスト内の任意位置からのパターンで全体の50%以上かつ4回以上

        Args:
            text: 検査対象テキスト
            min_pattern_len: 検出対象の最小パターン長
            max_pattern_len: 検出対象の最大パターン長

        Returns:
            bool: 繰り返しパターンが検出された場合True
        """
        text_len = len(text)
        if text_len < min_pattern_len * 3:
            return False

        effective_max = min(max_pattern_len + 1, text_len // 2 + 1)

        # --- 方式1: 先頭起点のパターン検査（従来方式、閾値を緩和） ---
        for pattern_len in range(min_pattern_len, effective_max):
            pattern = text[:pattern_len]
            count = text.count(pattern)
            coverage = (count * pattern_len) / text_len
            if count >= 3 and coverage >= 0.6:
                return True

        # --- 方式2: スライディングウィンドウによる任意位置パターン検査 ---
        # テキストが十分長い場合のみ実行（コスト軽減）
        if text_len >= 30:
            # 検査するパターン長を間引いて効率化
            pattern_lengths = list(range(
                min_pattern_len,
                min(max_pattern_len + 1, text_len // 3 + 1),
                max(1, (max_pattern_len - min_pattern_len) // 10),
            ))
            # 句読点区切りの長さも追加（日本語の繰り返しフレーズ検出用）
            for sep in ["。", "、", "！", "？"]:
                parts = [p for p in text.split(sep) if p.strip()]
                if parts:
                    phrase_len = len(parts[0].strip()) + 1  # 句読点を含む長さ
                    if min_pattern_len <= phrase_len <= max_pattern_len:
                        pattern_lengths.append(phrase_len)

            for pattern_len in pattern_lengths:
                # テキスト内の複数の開始位置からパターンを試す
                step = max(1, text_len // 8)
                for start in range(0, text_len - pattern_len, step):
                    pattern = text[start:start + pattern_len]
                    # 空白や句読点のみのパターンはスキップ
                    stripped = pattern.replace("。", "").replace("、", "").replace(" ", "").replace("　", "")
                    if len(stripped) < min_pattern_len:
                        continue
                    count = text.count(pattern)
                    coverage = (count * pattern_len) / text_len
                    if count >= 4 and coverage >= 0.5:
                        return True

        return False

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
