"""
システム情報APIルート

サーバーのハードウェア情報とWhisperモデル推奨設定を提供するエンドポイント。
"""

import logging

from fastapi import APIRouter

from app.services.system_info import SystemInfoService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["システム情報"])

# サービスインスタンス
_system_info_service = SystemInfoService()


@router.get(
    "/info",
    summary="システム情報取得",
    description="サーバーのCPU、RAM、GPU情報とWhisperモデル推奨設定を返す。",
)
async def get_system_info() -> dict:
    """
    サーバーのハードウェア情報を取得する。

    Returns:
        CPU、RAM、GPU、プラットフォーム情報、利用可能なWhisperモデル一覧、推奨設定
    """
    return _system_info_service.get_system_info()
