"""
APIパッケージ

FastAPIルーターの集約と登録を行う。
"""

from fastapi import APIRouter

from app.api.routes import export, jobs, upload

# メインAPIルーターの作成
api_router = APIRouter(prefix="/api")

# 各サブルーターの登録
api_router.include_router(upload.router, tags=["アップロード"])
api_router.include_router(jobs.router, tags=["ジョブ管理"])
api_router.include_router(export.router, tags=["エクスポート"])
