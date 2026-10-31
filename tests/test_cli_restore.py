"""Testes do comando de restauração e seed inicial a partir de dados/."""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import async_sessionmaker

from aurora.config import get_settings
from aurora.db import (
    ReservaRepository,
    VisitanteRepository,
    create_db_engine,
    ensure_seeded_if_empty,
    restore_initial_data,
)


async def test_restore_initial_data_reloads_initial_records_and_preserves_on_ensure() -> None:
    settings = get_settings()
    engine = create_db_engine(settings.database_url)
    try:
        await restore_initial_data(engine, settings.dados_dir)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as session:
            res_101 = await ReservaRepository.listar_ativas_por_apartamento(
                session, "101"
            )
            assert res_101 == [
                {"codigo": "RSV-1377", "area": "quadra", "data": "2030-03-09"}
            ]

            vis_302 = await VisitanteRepository.listar_por_apartamento(
                session, "302"
            )
            assert vis_302 == [{"nome": "Marina Duarte", "data": "2030-03-16"}]

            # Faz uma alteração e garante que ensure_seeded_if_empty NÃO sobrescreve
            nova = await ReservaRepository.criar_atomica(
                session,
                apartamento="101",
                area_id="quadra",
                data_reserva=date(2030, 4, 6),
            )
            assert nova.sucesso is True
            assert nova.codigo == "RSV-5000"

        seeded = await ensure_seeded_if_empty(engine, settings.dados_dir)
        assert seeded is False

        async with session_factory() as session:
            res_101_apos = await ReservaRepository.listar_ativas_por_apartamento(
                session, "101"
            )
            assert len(res_101_apos) == 2

        # Restaurar novamente volta ao estado inicial
        await restore_initial_data(engine, settings.dados_dir)
        async with session_factory() as session:
            res_101_reset = await ReservaRepository.listar_ativas_por_apartamento(
                session, "101"
            )
            assert res_101_reset == [
                {"codigo": "RSV-1377", "area": "quadra", "data": "2030-03-09"}
            ]
    finally:
        await engine.dispose()
