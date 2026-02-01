"""
TranscriberServiceのユニットテスト

ハルシネーション検出ロジックのテストを中心に行う。
Whisperモデルのロード・推論はモック化してテストする。
"""

import pytest

from app.services.transcriber import TranscriberService


class TestIsRepetitiveText:
    """_is_repetitive_text メソッドのテスト"""

    def test_short_text_not_repetitive(self):
        """短いテキストは繰り返しと判定しない"""
        assert TranscriberService._is_repetitive_text("こんにちは") is False

    def test_normal_text_not_repetitive(self):
        """通常の文章は繰り返しと判定しない"""
        text = "今日は天気がいいですね。明日も晴れるそうです。"
        assert TranscriberService._is_repetitive_text(text) is False

    def test_simple_repetition_from_start(self):
        """先頭からの単純な繰り返しを検出する"""
        text = "あああああああああああああああああああ"
        assert TranscriberService._is_repetitive_text(text) is True

    def test_phrase_repetition_from_start(self):
        """先頭からのフレーズ繰り返しを検出する"""
        text = "私たちの人気がありません。" * 10
        assert TranscriberService._is_repetitive_text(text) is True

    def test_phrase_repetition_from_middle(self):
        """途中からのフレーズ繰り返しを検出する（error4.txtの典型パターン）"""
        text = "効果あります。ちょっと意味じゃ。" + "私たちの人気がありません。" * 20
        assert TranscriberService._is_repetitive_text(text) is True

    def test_mixed_repetition_with_prefix(self):
        """前半に正常テキスト、後半に繰り返しがあるケースを検出する"""
        normal = "みなさん、ありがとうございます。"
        repeated = "ご視聴ありがとうございました。" * 15
        text = normal + repeated
        assert TranscriberService._is_repetitive_text(text) is True

    def test_empty_string(self):
        """空文字列は繰り返しでない"""
        assert TranscriberService._is_repetitive_text("") is False

    def test_single_character_repetition(self):
        """1文字の大量繰り返しを検出する"""
        text = "あ" * 100
        assert TranscriberService._is_repetitive_text(text) is True

    def test_two_different_sentences(self):
        """2つの異なる文は繰り返しと判定しない"""
        text = "今日は良い天気です。明日も良い天気だといいですね。"
        assert TranscriberService._is_repetitive_text(text) is False

    def test_similar_but_not_identical_sentences(self):
        """似ているが同一でない文は繰り返しと判定しない"""
        text = "第1章では基礎を学びます。第2章では応用を学びます。第3章では実践を学びます。"
        assert TranscriberService._is_repetitive_text(text) is False


class TestExtractCorePhrase:
    """_extract_core_phrase メソッドのテスト"""

    def test_single_sentence(self):
        """1文のテキストから主要フレーズを抽出する"""
        result = TranscriberService._extract_core_phrase("これはテストです。")
        assert result == "これはテストです"

    def test_multiple_sentences(self):
        """複数文のテキストから最長フレーズを抽出する"""
        result = TranscriberService._extract_core_phrase("短い。これは長いフレーズです。中くらい。")
        assert result == "これは長いフレーズです"

    def test_empty_text(self):
        """空テキストはNoneを返す"""
        result = TranscriberService._extract_core_phrase("")
        assert result is None

    def test_max_len_truncation(self):
        """最大長を超える場合は切り詰める"""
        long_text = "あ" * 100
        result = TranscriberService._extract_core_phrase(long_text, max_len=10)
        assert len(result) == 10


class TestProcessSegments:
    """_process_segments メソッドのテスト"""

    def setup_method(self):
        """各テスト前にTranscriberServiceインスタンスを初期化"""
        # シングルトンのリセット
        TranscriberService._instance = None
        TranscriberService._model = None
        TranscriberService._model_loaded = False
        self.service = TranscriberService()

    def test_normal_segments(self):
        """正常なセグメントを正しく処理する"""
        raw = [
            {"text": "こんにちは。", "start": 0.0, "end": 2.0, "no_speech_prob": 0.1},
            {"text": "元気ですか。", "start": 2.0, "end": 4.0, "no_speech_prob": 0.05},
        ]
        result = self.service._process_segments(raw)
        assert len(result) == 2
        assert result[0]["text"] == "こんにちは。"
        assert result[1]["text"] == "元気ですか。"
        assert result[0]["segment_index"] == 0
        assert result[1]["segment_index"] == 1

    def test_empty_text_filtered(self):
        """空テキストのセグメントが除外される"""
        raw = [
            {"text": "こんにちは。", "start": 0.0, "end": 2.0, "no_speech_prob": 0.1},
            {"text": "  ", "start": 2.0, "end": 4.0, "no_speech_prob": 0.1},
            {"text": "さようなら。", "start": 4.0, "end": 6.0, "no_speech_prob": 0.1},
        ]
        result = self.service._process_segments(raw)
        assert len(result) == 2

    def test_high_no_speech_prob_filtered(self):
        """無音確率が高いセグメントが除外される"""
        raw = [
            {"text": "こんにちは。", "start": 0.0, "end": 2.0, "no_speech_prob": 0.1},
            {"text": "ノイズ", "start": 2.0, "end": 4.0, "no_speech_prob": 0.9},
        ]
        result = self.service._process_segments(raw)
        assert len(result) == 1
        assert result[0]["text"] == "こんにちは。"

    def test_consecutive_same_text_filtered(self):
        """連続する同一テキストが除外される"""
        raw = [
            {"text": "テスト。", "start": 0.0, "end": 2.0, "no_speech_prob": 0.1},
            {"text": "テスト。", "start": 2.0, "end": 4.0, "no_speech_prob": 0.1},
            {"text": "テスト。", "start": 4.0, "end": 6.0, "no_speech_prob": 0.1},
        ]
        result = self.service._process_segments(raw)
        assert len(result) == 1

    def test_repetitive_text_within_segment_filtered(self):
        """セグメント内の繰り返しテキストが除外される"""
        raw = [
            {"text": "正常なテキスト。", "start": 0.0, "end": 2.0, "no_speech_prob": 0.1},
            {"text": "繰り返し。" * 20, "start": 2.0, "end": 30.0, "no_speech_prob": 0.1},
        ]
        result = self.service._process_segments(raw)
        assert len(result) == 1
        assert result[0]["text"] == "正常なテキスト。"

    def test_consecutive_similar_segments_filtered(self):
        """連続する類似セグメントが閾値を超えた場合に除外される"""
        raw = [
            {"text": "正常なテキスト。", "start": 0.0, "end": 2.0, "no_speech_prob": 0.1},
        ]
        # 同じ主要フレーズを含む連続セグメントを追加
        for i in range(10):
            raw.append({
                "text": f"私たちの人気がありません。追加テキスト{i}。",
                "start": 2.0 + i * 2,
                "end": 4.0 + i * 2,
                "no_speech_prob": 0.1,
            })
        result = self.service._process_segments(raw)
        # 最初の正常テキスト + 閾値以下の類似セグメントのみ残る
        assert len(result) < 11

    def test_confidence_calculation(self):
        """信頼度スコアが正しく計算される"""
        raw = [
            {"text": "テスト。", "start": 0.0, "end": 2.0, "no_speech_prob": 0.3},
        ]
        result = self.service._process_segments(raw)
        assert result[0]["confidence"] == 0.7

    def test_segment_index_renumbering(self):
        """フィルタリング後のセグメントインデックスが連番に再採番される"""
        raw = [
            {"text": "最初。", "start": 0.0, "end": 2.0, "no_speech_prob": 0.1},
            {"text": "", "start": 2.0, "end": 4.0, "no_speech_prob": 0.1},  # 除外される
            {"text": "最後。", "start": 4.0, "end": 6.0, "no_speech_prob": 0.1},
        ]
        result = self.service._process_segments(raw)
        assert result[0]["segment_index"] == 0
        assert result[1]["segment_index"] == 1

    def test_time_rounding(self):
        """時間が小数点3桁に丸められる"""
        raw = [
            {"text": "テスト。", "start": 1.23456789, "end": 3.98765432, "no_speech_prob": 0.1},
        ]
        result = self.service._process_segments(raw)
        assert result[0]["start_time"] == 1.235
        assert result[0]["end_time"] == 3.988
