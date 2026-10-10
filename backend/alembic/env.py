"""Alembic 环境：元数据来自 ORM（单一事实源），URL 走 TRUEORDER_ 配置。"""

from __future__ import annotations

import os

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.infrastructure.orm import Base

config = context.config
target_metadata = Base.metadata


def _database_url() -> str:
    # 优先级：命令行 -x url= > 环境变量 TRUEORDER_DATABASE_URL > ini sqlalchemy.url
    x_url = context.get_x_argument(as_dictionary=True).get("url")
    if x_url:
        return x_url
    env_url = os.environ.get("TRUEORDER_DATABASE_URL")
    if env_url:
        return env_url
    return config.get_main_option("sqlalchemy.url")


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
