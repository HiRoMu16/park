"""
テスト共通フィクスチャ

SQLite In-Memoryを使用したテスト用DBセッション、
FastAPI TestClientの提供を行う。
"""

import asyncio
from collections.abc import AsyncGenerator
from typing import Generator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import Base, get_db


# テスト用SQLite非同期エンジン（aiosqliteドライバ使用）
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
)

TestSessionFactory = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """テスト全体で共有するイベントループ"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    """各テスト前にテーブルを作成し、テスト後に削除する"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """テスト用DBセッション"""
    async with TestSessionFactory() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    テスト用HTTPクライアント

    FastAPIのget_db依存をテスト用セッションで差し替える。
    redis_subscriberのstart/stopはモック化して回避する。
    """
    from unittest.mock import AsyncMock, patch

    # FastAPIアプリのget_dbをテスト用セッションに差し替え
    async def override_get_db():
        yield db_session

    # redis_subscriberをモック化（Redis不要でテスト可能にする）
    mock_subscriber = AsyncMock()

    with patch("app.main.redis_subscriber", mock_subscriber):
        # パッチ適用後にアプリをインポート
        from app.main import app

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

        app.dependency_overrides.clear()
