"""Testes de criação do schema PostgreSQL (tabelas, sequência e índice parcial)."""

from __future__ import annotations

from sqlalchemy import text

from aurora.db import create_db_engine, init_domain_schema


async def test_init_domain_schema_creates_tables_sequence_and_partial_index() -> None:
    engine = create_db_engine()
    try:
        await init_domain_schema(engine)

        async with engine.connect() as conn:
            tables_result = await conn.execute(
                text(
                    """
                    SELECT tablename
                    FROM pg_tables
                    WHERE schemaname = 'public'
                    """
                )
            )
            tables = {row[0] for row in tables_result.fetchall()}
            assert {
                "apartamentos",
                "areas",
                "reservas",
                "visitantes",
                "confirmacoes_pendentes",
            }.issubset(tables)

            seq_result = await conn.execute(
                text(
                    """
                    SELECT sequencename
                    FROM pg_sequences
                    WHERE schemaname = 'public'
                      AND sequencename = 'reserva_codigo_seq'
                    """
                )
            )
            assert seq_result.scalar_one_or_none() == "reserva_codigo_seq"

            idx_result = await conn.execute(
                text(
                    """
                    SELECT indexdef
                    FROM pg_indexes
                    WHERE schemaname = 'public'
                      AND tablename = 'reservas'
                      AND indexname = 'uq_reservas_area_data_ativa'
                    """
                )
            )
            indexdef = idx_result.scalar_one_or_none()
            assert indexdef is not None
            assert "UNIQUE INDEX" in indexdef
            assert "WHERE (ativa = true)" in indexdef
    finally:
        await engine.dispose()
