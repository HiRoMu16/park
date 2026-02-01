"""
Alembicマイグレーション環境設定

asyncpgを使用した非同期マイグレーション実行をサポートする。
app.database.BaseのメタデータとSQLAlchemyモデルを自動認識する。
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import settings
from app.database import Base

# Alembicの設定オブジェクト
config = context.config

# ログ設定の読み込み
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# SQLAlchemyモデルのメタデータ（テーブル定義を自動検出するために必要）
# app.models内のモデルがBaseを継承しているため、importするだけで認識される
import app.models.job  # noqa: F401

target_metadata = Base.metadata

# データベースURLの動的設定（settings.DATABASE_URLから取得）
# alembic.iniのsqlalchemy.urlを上書きする
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)


def run_migrations_offline() -> None:
    """
    オフラインマイグレーション（SQL出力モード）

    DB接続せずにマイグレーションSQLを出力する。
    `alembic upgrade head --sql` で使用される。
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """同期コンテキストでマイグレーションを実行する"""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    非同期マイグレーション実行

    asyncpg対応のAsyncEngineを使用してマイグレーションを実行する。
    """
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """
    オンラインマイグレーション（DB接続モード）

    asyncpg経由でPostgreSQLに接続し、マイグレーションを実行する。
    通常の `alembic upgrade head` で使用される。
    """
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
