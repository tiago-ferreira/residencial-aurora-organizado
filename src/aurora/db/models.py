"""Modelos SQLAlchemy e schema PostgreSQL do domínio do Residencial Aurora."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Sequence,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class DomainBase(DeclarativeBase):
    """Base declarativa isolada das tabelas internas do Google ADK."""


reserva_codigo_seq = Sequence(
    "reserva_codigo_seq",
    start=5000,
    increment=1,
    metadata=DomainBase.metadata,
)


class ApartamentoModel(DomainBase):
    """Cadastro de apartamentos e moradores do condomínio."""

    __tablename__ = "apartamentos"

    numero: Mapped[str] = mapped_column(String(20), primary_key=True)
    morador: Mapped[str] = mapped_column(String(200), nullable=False)


class AreaModel(DomainBase):
    """Áreas comuns reserváveis e suas respectivas taxas."""

    __tablename__ = "areas"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    taxa: Mapped[float] = mapped_column(
        Numeric(10, 2, asdecimal=False), nullable=False
    )


class ReservaModel(DomainBase):
    """Reservas de áreas comuns com exclusividade ativa por (area_id, data)."""

    __tablename__ = "reservas"

    codigo: Mapped[str] = mapped_column(String(64), primary_key=True)
    apartamento: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )
    area_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("areas.id"), nullable=False
    )
    data: Mapped[date] = mapped_column(Date, nullable=False)
    ativa: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index(
            "uq_reservas_area_data_ativa",
            "area_id",
            "data",
            unique=True,
            postgresql_where=text("ativa = true"),
        ),
    )


class VisitanteModel(DomainBase):
    """Autorizações de entrada de visitantes registradas por apartamento."""

    __tablename__ = "visitantes"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    apartamento: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    data: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ConfirmacaoPendenteModel(DomainBase):
    """Controle transacional e idempotente de confirmações pendentes de tools."""

    __tablename__ = "confirmacoes_pendentes"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True
    )
    apartamento: Mapped[str] = mapped_column(String(20), nullable=False)
    invocation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    acao: Mapped[str] = mapped_column(String(128), nullable=False)
    detalhes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="PENDENTE",
        server_default=text("'PENDENTE'"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


async def init_domain_schema(engine: AsyncEngine) -> None:
    """Cria de forma idempotente sequências, tabelas e índices do domínio."""
    async with engine.begin() as conn:
        await conn.run_sync(DomainBase.metadata.create_all)
