"""
ファイル管理サービス

チャンクアップロード、ファイル結合、ファイル削除などの
ファイルシステム操作を一元管理する。
"""

import logging
import shutil
from pathlib import Path
from typing import Optional

import aiofiles

from app.config import settings

logger = logging.getLogger(__name__)


class FileManager:
    """
    ファイル管理サービス

    チャンクアップロードの保存・結合、ジョブ関連ファイルの管理を行う。
    """

    def __init__(self) -> None:
        """ディレクトリパスの初期化"""
        self._upload_dir = settings.UPLOAD_DIR
        self._processed_dir = settings.PROCESSED_DIR
        self._temp_dir = settings.TEMP_DIR

    def _get_chunk_dir(self, job_id: str) -> Path:
        """ジョブ固有のチャンク一時ディレクトリを取得する"""
        return self._temp_dir / f"chunks_{job_id}"

    def _get_chunk_path(self, job_id: str, chunk_index: int) -> Path:
        """個別チャンクファイルのパスを取得する"""
        chunk_dir = self._get_chunk_dir(job_id)
        return chunk_dir / f"chunk_{chunk_index:06d}"

    async def save_chunk(
        self,
        job_id: str,
        chunk_index: int,
        chunk_data: bytes,
    ) -> Path:
        """
        チャンクデータをファイルに保存する。

        Args:
            job_id: ジョブID
            chunk_index: チャンクのインデックス番号
            chunk_data: チャンクのバイナリデータ

        Returns:
            Path: 保存されたチャンクファイルのパス
        """
        chunk_dir = self._get_chunk_dir(job_id)
        chunk_dir.mkdir(parents=True, exist_ok=True)

        chunk_path = self._get_chunk_path(job_id, chunk_index)

        # 非同期でチャンクファイルを書き込み
        async with aiofiles.open(chunk_path, "wb") as f:
            await f.write(chunk_data)

        logger.debug(
            "チャンク保存: job_id=%s, chunk_index=%d, size=%d bytes",
            job_id,
            chunk_index,
            len(chunk_data),
        )

        return chunk_path

    async def merge_chunks(
        self,
        job_id: str,
        total_chunks: int,
        original_filename: str,
    ) -> Path:
        """
        全チャンクを結合して1つのファイルにする。

        Args:
            job_id: ジョブID
            total_chunks: 全チャンク数
            original_filename: 元のファイル名（拡張子を取得するため）

        Returns:
            Path: 結合されたファイルのパス

        Raises:
            FileNotFoundError: チャンクファイルが不足している場合
        """
        # 出力ファイルパスの決定
        ext = Path(original_filename).suffix
        output_path = self._upload_dir / f"{job_id}{ext}"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(
            "チャンク結合開始: job_id=%s, total_chunks=%d, output=%s",
            job_id,
            total_chunks,
            output_path,
        )

        # 全チャンクの存在確認
        missing_chunks = []
        for i in range(total_chunks):
            chunk_path = self._get_chunk_path(job_id, i)
            if not chunk_path.exists():
                missing_chunks.append(i)

        if missing_chunks:
            raise FileNotFoundError(
                f"以下のチャンクが見つかりません: {missing_chunks}"
            )

        # チャンクをインデックス順に結合
        async with aiofiles.open(output_path, "wb") as output_file:
            for i in range(total_chunks):
                chunk_path = self._get_chunk_path(job_id, i)
                async with aiofiles.open(chunk_path, "rb") as chunk_file:
                    while True:
                        # メモリ効率のため、1MBずつ読み込んで書き込む
                        data = await chunk_file.read(1024 * 1024)
                        if not data:
                            break
                        await output_file.write(data)

        file_size = output_path.stat().st_size
        logger.info(
            "チャンク結合完了: job_id=%s, output=%s, size=%d bytes",
            job_id,
            output_path,
            file_size,
        )

        return output_path

    async def cleanup_chunks(self, job_id: str) -> None:
        """
        チャンクの一時ファイルとディレクトリを削除する。

        Args:
            job_id: ジョブID
        """
        chunk_dir = self._get_chunk_dir(job_id)

        if chunk_dir.exists():
            shutil.rmtree(str(chunk_dir), ignore_errors=True)
            logger.info("チャンクファイル削除完了: job_id=%s", job_id)
        else:
            logger.debug("チャンクディレクトリが存在しません: job_id=%s", job_id)

    async def cleanup_job_files(self, job_id: str) -> None:
        """
        ジョブに関連する全ファイルを削除する。

        アップロードファイル、処理済みファイル、チャンク一時ファイルを含む。

        Args:
            job_id: ジョブID
        """
        deleted_files = []

        # アップロードディレクトリ内のジョブ関連ファイルを削除
        for file_path in self._upload_dir.glob(f"{job_id}*"):
            file_path.unlink(missing_ok=True)
            deleted_files.append(str(file_path))

        # 処理済みディレクトリ内のジョブ関連ファイルを削除
        for file_path in self._processed_dir.glob(f"{job_id}*"):
            file_path.unlink(missing_ok=True)
            deleted_files.append(str(file_path))

        # チャンク一時ファイルの削除
        await self.cleanup_chunks(job_id)

        logger.info(
            "ジョブファイル全削除完了: job_id=%s, 削除ファイル数=%d",
            job_id,
            len(deleted_files),
        )

    def get_file_path(
        self,
        job_id: str,
        file_type: str = "upload",
        extension: str = "",
    ) -> Path:
        """
        ジョブのファイルパスを取得する。

        Args:
            job_id: ジョブID
            file_type: ファイル種別（"upload", "processed", "audio"）
            extension: ファイル拡張子（例: ".mp4", ".wav"）

        Returns:
            Path: ファイルパス
        """
        if file_type == "upload":
            return self._upload_dir / f"{job_id}{extension}"
        elif file_type == "processed" or file_type == "audio":
            return self._processed_dir / f"{job_id}.wav"
        else:
            raise ValueError(f"不明なファイル種別: {file_type}")

    def check_disk_space(self, required_bytes: int = 0) -> dict:
        """
        ディスクの空き容量を確認する。

        Args:
            required_bytes: 必要なバイト数（0の場合は確認のみ）

        Returns:
            dict: ディスク容量情報（total, used, free, sufficient）
        """
        disk_usage = shutil.disk_usage(str(self._upload_dir))

        result = {
            "total": disk_usage.total,
            "used": disk_usage.used,
            "free": disk_usage.free,
            "free_gb": round(disk_usage.free / (1024 ** 3), 2),
            "sufficient": True,
        }

        if required_bytes > 0:
            # 必要容量の2倍のマージンを確保（処理中の中間ファイル用）
            result["sufficient"] = disk_usage.free >= required_bytes * 2

        return result
