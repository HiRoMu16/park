"""
WebSocket接続管理モジュール

ジョブの進捗をリアルタイムにクライアントへ通知する。
各ジョブIDに対して複数のクライアント接続を管理する。
"""

import json
import logging
from typing import Dict, List

from fastapi import WebSocket, WebSocketDisconnect

from app.schemas.job import ProgressUpdate

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    WebSocket接続マネージャー

    ジョブIDごとにWebSocket接続を管理し、
    進捗更新メッセージをブロードキャストする。
    """

    def __init__(self) -> None:
        """接続マップの初期化"""
        # ジョブIDをキー、WebSocket接続リストを値とするマッピング
        self._connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, job_id: str) -> None:
        """
        WebSocket接続を受け入れ、接続マップに登録する。

        Args:
            websocket: WebSocket接続オブジェクト
            job_id: 対象ジョブのID
        """
        await websocket.accept()
        if job_id not in self._connections:
            self._connections[job_id] = []
        self._connections[job_id].append(websocket)
        logger.info(
            "WebSocket接続: job_id=%s, 現在の接続数=%d",
            job_id,
            len(self._connections[job_id]),
        )

    def disconnect(self, websocket: WebSocket, job_id: str) -> None:
        """
        WebSocket接続を解除し、接続マップから削除する。

        Args:
            websocket: WebSocket接続オブジェクト
            job_id: 対象ジョブのID
        """
        if job_id in self._connections:
            self._connections[job_id] = [
                conn for conn in self._connections[job_id] if conn != websocket
            ]
            # 接続がなくなったらキー自体を削除
            if not self._connections[job_id]:
                del self._connections[job_id]
        logger.info("WebSocket切断: job_id=%s", job_id)

    async def send_progress(self, job_id: str, update: ProgressUpdate) -> None:
        """
        指定ジョブIDの全接続に進捗更新メッセージを送信する。

        切断済みの接続は自動的に除外する。

        Args:
            job_id: 対象ジョブのID
            update: 進捗更新データ
        """
        if job_id not in self._connections:
            return

        message = update.model_dump_json()
        disconnected: List[WebSocket] = []

        for connection in self._connections[job_id]:
            try:
                await connection.send_text(message)
            except Exception as e:
                # 送信失敗した接続は切断済みとしてマーク
                logger.warning(
                    "WebSocket送信失敗: job_id=%s, error=%s",
                    job_id,
                    str(e),
                )
                disconnected.append(connection)

        # 切断済み接続の削除
        for conn in disconnected:
            self.disconnect(conn, job_id)

    async def broadcast(self, message: str) -> None:
        """
        全接続にメッセージをブロードキャストする。

        Args:
            message: 送信するメッセージ文字列
        """
        for job_id in list(self._connections.keys()):
            disconnected: List[WebSocket] = []
            for connection in self._connections[job_id]:
                try:
                    await connection.send_text(message)
                except Exception:
                    disconnected.append(connection)
            for conn in disconnected:
                self.disconnect(conn, job_id)

    def get_connection_count(self, job_id: str | None = None) -> int:
        """
        接続数を取得する。

        Args:
            job_id: 指定した場合はそのジョブの接続数。Noneの場合は全接続数。

        Returns:
            int: 接続数
        """
        if job_id:
            return len(self._connections.get(job_id, []))
        return sum(len(conns) for conns in self._connections.values())


# シングルトンインスタンス（アプリケーション全体で共有）
manager = ConnectionManager()


async def websocket_endpoint(websocket: WebSocket, job_id: str) -> None:
    """
    WebSocketエンドポイントハンドラー

    クライアントからの接続を受け入れ、切断まで維持する。
    進捗更新はサーバー側（Celeryワーカー等）からpushされる。

    Args:
        websocket: WebSocket接続オブジェクト
        job_id: 監視対象のジョブID
    """
    await manager.connect(websocket, job_id)
    try:
        while True:
            # クライアントからのメッセージを待機（keepalive）
            data = await websocket.receive_text()
            # ping/pongメッセージへの応答
            if data == "ping":
                await websocket.send_text(
                    json.dumps({"type": "pong"})
                )
    except WebSocketDisconnect:
        manager.disconnect(websocket, job_id)
        logger.info("WebSocket正常切断: job_id=%s", job_id)
    except Exception as e:
        manager.disconnect(websocket, job_id)
        logger.error(
            "WebSocketエラー: job_id=%s, error=%s",
            job_id,
            str(e),
        )
