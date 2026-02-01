"""
Redis Pub/Sub進捗更新リスナー

CeleryワーカーがRedis Pub/Subチャンネルに発行した進捗メッセージを
受信し、WebSocket ConnectionManager経由でクライアントに転送する。

データフロー:
    Celery Worker --publish--> Redis Pub/Sub --subscribe--> このモジュール
    --> ConnectionManager.send_progress() --> WebSocket --> ブラウザ
"""

import asyncio
import json
import logging

import redis.asyncio as aioredis

from app.api.websocket import manager
from app.config import settings
from app.schemas.job import ProgressUpdate

logger = logging.getLogger(__name__)


class RedisProgressSubscriber:
    """
    Redis Pub/Subサブスクライバー

    job_progress:* パターンにマッチするチャンネルを購読し、
    受信したメッセージをWebSocket経由でクライアントに転送する。
    """

    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None
        self._pubsub: aioredis.client.PubSub | None = None
        self._task: asyncio.Task | None = None
        self._running: bool = False

    async def start(self) -> None:
        """
        サブスクライバーを起動する。

        Redis接続を確立し、パターンサブスクライブを開始し、
        メッセージリスニングのバックグラウンドタスクを作成する。
        """
        try:
            self._redis = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
            )
            self._pubsub = self._redis.pubsub()
            await self._pubsub.psubscribe("job_progress:*")
            self._running = True
            self._task = asyncio.create_task(self._listen())
            logger.info(
                "Redis Pub/Subサブスクライバーを起動しました: pattern=job_progress:*"
            )
        except Exception as e:
            logger.error(
                "Redis Pub/Subサブスクライバーの起動に失敗しました: %s", str(e)
            )
            self._running = False

    async def stop(self) -> None:
        """
        サブスクライバーを停止する。

        バックグラウンドタスクをキャンセルし、Redis接続を閉じる。
        """
        self._running = False

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        if self._pubsub:
            try:
                await self._pubsub.punsubscribe("job_progress:*")
                await self._pubsub.close()
            except Exception:
                pass
            self._pubsub = None

        if self._redis:
            try:
                await self._redis.close()
            except Exception:
                pass
            self._redis = None

        logger.info("Redis Pub/Subサブスクライバーを停止しました。")

    async def _listen(self) -> None:
        """
        Redis Pub/Subメッセージを継続的にリスニングする。

        パターンマッチしたメッセージを受信するたびに、
        チャンネル名からjob_idを抽出し、ConnectionManagerに転送する。
        """
        try:
            while self._running:
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message is None:
                    # タイムアウト — 次のイテレーションへ
                    await asyncio.sleep(0.01)
                    continue

                if message["type"] == "pmessage":
                    await self._handle_message(message)

        except asyncio.CancelledError:
            logger.debug("Redis Pub/Subリスナータスクがキャンセルされました。")
        except Exception as e:
            logger.error(
                "Redis Pub/Subリスナーでエラーが発生しました: %s",
                str(e),
                exc_info=True,
            )

    async def _handle_message(self, message: dict) -> None:
        """
        受信したPub/Subメッセージを処理する。

        チャンネル名（job_progress:{job_id}）からjob_idを抽出し、
        メッセージデータをProgressUpdateに変換してConnectionManagerに送信する。
        """
        try:
            channel = message["channel"]
            # チャンネル名からjob_idを抽出: "job_progress:xxxx" -> "xxxx"
            job_id = channel.split(":", 1)[1] if ":" in channel else None
            if not job_id:
                return

            data = json.loads(message["data"])
            update = ProgressUpdate(
                job_id=data.get("job_id", job_id),
                status=data.get("status", ""),
                progress=data.get("progress", 0.0),
                message=data.get("message", ""),
            )

            await manager.send_progress(job_id, update)

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(
                "Redis Pub/Subメッセージの処理に失敗しました: %s", str(e)
            )


# シングルトンインスタンス
redis_subscriber = RedisProgressSubscriber()
