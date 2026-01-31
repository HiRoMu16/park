"""
Celeryワーカーパッケージ

非同期タスク処理のためのCeleryアプリケーションとタスク定義。
Redis をブローカーおよび結果バックエンドとして使用する。
"""

from celery import Celery

from app.config import settings

# Celeryアプリケーションの初期化
celery_app = Celery(
    "voice2character",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# Celery設定
celery_app.conf.update(
    # タスクのシリアライゼーション形式
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # タイムゾーン設定
    timezone="Asia/Tokyo",
    enable_utc=True,

    # タスク実行設定
    task_track_started=True,       # タスク開始時にSTARTEDステートを記録
    task_acks_late=True,           # タスク完了後にACK（ワーカー障害時の再実行保証）
    worker_prefetch_multiplier=1,  # 1タスクずつ取得（大量メモリ消費タスク向け）

    # リトライ設定
    task_default_retry_delay=60,   # リトライ間隔（秒）
    task_max_retries=3,            # 最大リトライ回数

    # 結果の有効期限（24時間）
    result_expires=86400,

    # ワーカーの同時実行数（Whisperは重いので1タスクずつ）
    worker_concurrency=1,
)

# タスクモジュールの自動検出
celery_app.autodiscover_tasks(["app.workers"])
