"""
データベース接続管理モジュール

SQLAlchemy AsyncSessionを使った非同期データベース接続を提供する。
PostgreSQLに対してasyncpgドライバで接続する。
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# 非同期エンジンの作成
# pool_sizeとmax_overflowで同時接続数を制御
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,  # 接続の有効性を事前に確認
    pool_recycle=3600,    # 1時間で接続をリサイクル
)

# セッションファクトリの作成
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # コミット後もオブジェクトのアトリビュートにアクセス可能
)


class Base(DeclarativeBase):
    """
    全SQLAlchemyモデルの基底クラス。

    DeclarativeBaseを使用し、テーブル定義の基盤となる。
    """
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    データベースセッションの依存性注入関数。

    FastAPIのDependsで使用し、リクエストごとにセッションを提供する。
    リクエスト完了後に自動的にセッションをクローズする。

    Yields:
        AsyncSession: 非同期データベースセッション
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_tables() -> None:
    """
    全テーブルを作成する。

    アプリケーション起動時に呼び出し、
    定義されたモデルに基づいてテーブルを自動作成する。
    既存のテーブルには影響しない。
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_engine() -> None:
    """
    データベースエンジンを破棄する。

    アプリケーション終了時に呼び出し、
    全ての接続プールを解放する。
    """
    await engine.dispose()
