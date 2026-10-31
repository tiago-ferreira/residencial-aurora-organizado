"""Gerenciamento de AsyncEngine e sessões SQLAlchemy para o PostgreSQL."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from aurora.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def create_db_engine(database_url: str | None = None) -> AsyncEngine:
    """Cria uma nova instância de AsyncEngine configurada para PostgreSQL."""
    url = database_url or get_settings().database_url
    return create_async_engine(url, pool_pre_ping=True)


def get_engine() -> AsyncEngine:
    """Retorna o AsyncEngine singleton do processo."""
    global _engine
    if _engine is None:
        _engine = create_db_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Retorna o async_sessionmaker associado ao engine global."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
        )
    return _session_factory


async def dispose_engine() -> None:
    """Fecha conexões do pool global (útil em shutdown e testes)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
