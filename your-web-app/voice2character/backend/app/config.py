"""
アプリケーション設定モジュール

pydantic-settingsを使用した環境変数ベースの設定管理。
.envファイルまたは環境変数から設定値を読み込む。
"""

from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    アプリケーション全体の設定クラス。

    環境変数または.envファイルから値を読み込む。
    デフォルト値は開発環境向けに設定されている。
    """

    # ---- アプリケーション基本設定 ----
    APP_NAME: str = "Voice2Character"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # ---- データベース設定 ----
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/voice2character"

    # ---- Redis設定 ----
    REDIS_URL: str = "redis://localhost:6379/0"

    # ---- ファイルストレージ設定 ----
    # アップロードされたファイルの保存先ディレクトリ
    UPLOAD_DIR: Path = Path("./uploads")
    # 処理済みファイル（抽出した音声等）の保存先ディレクトリ
    PROCESSED_DIR: Path = Path("./processed")
    # チャンクアップロード用一時ディレクトリ
    TEMP_DIR: Path = Path("./tmp")

    # ---- ファイルアップロード制限 ----
    # 最大ファイルサイズ（バイト単位）: デフォルト5GB
    MAX_FILE_SIZE: int = 5 * 1024 * 1024 * 1024
    # 許可するファイル拡張子
    ALLOWED_EXTENSIONS: List[str] = [
        "mp4", "avi", "mov", "mkv", "webm",
        "m4a", "mp3", "wav", "flac",
    ]
    # チャンクアップロードの1チャンクサイズ（バイト単位）: デフォルト100MB
    CHUNK_SIZE: int = 100 * 1024 * 1024

    # ---- Whisper設定 ----
    # 使用するWhisperモデル名
    WHISPER_MODEL: str = "large-v3"
    # 推論デバイス（auto: GPU利用可能ならCUDA、なければCPU）
    WHISPER_DEVICE: str = "auto"
    # Whisperモデルの保存ディレクトリ（Dockerイメージではプリダウンロード済み）
    WHISPER_MODEL_DIR: str | None = None

    # ---- CORS設定 ----
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    # ---- Celeryワーカー設定 ----
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    @field_validator("UPLOAD_DIR", "PROCESSED_DIR", "TEMP_DIR", mode="before")
    @classmethod
    def convert_to_path(cls, v: str | Path) -> Path:
        """文字列をPathオブジェクトに変換する"""
        return Path(v) if isinstance(v, str) else v

    def setup_directories(self) -> None:
        """
        必要なディレクトリを作成する。

        アプリケーション起動時に呼び出し、
        アップロード・処理済み・一時ファイル用ディレクトリを自動作成する。
        """
        for directory in [self.UPLOAD_DIR, self.PROCESSED_DIR, self.TEMP_DIR]:
            directory.mkdir(parents=True, exist_ok=True)

    def get_whisper_device(self) -> str:
        """
        Whisperの推論デバイスを決定する。

        'auto'の場合はCUDAの利用可能性を自動検出する。
        """
        if self.WHISPER_DEVICE == "auto":
            try:
                import torch
                return "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                return "cpu"
        return self.WHISPER_DEVICE

    def is_allowed_extension(self, filename: str) -> bool:
        """ファイル拡張子が許可リストに含まれるか確認する"""
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        return ext in self.ALLOWED_EXTENSIONS

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


# シングルトンインスタンス（アプリケーション全体で共有）
settings = Settings()
