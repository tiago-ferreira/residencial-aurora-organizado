"""Testes transacionais, de isolamento e de concorrência contra o PostgreSQL."""

from __future__ import annotations

import asyncio
from datetime import date

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aurora.db import (
    AreaModel,
    ReservaModel,
    ReservaRepository,
    VisitanteModel,
    VisitanteRepository,
    create_db_engine,
    init_domain_schema,
)


async def _prepare_clean_db(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        await session.execute(delete(ReservaModel))
        await session.execute(delete(VisitanteModel))
        await session.execute(delete(AreaModel))
        session.add_all(
            [
                AreaModel(
                    id="salao-de-festas", nome="Salão de festas", taxa=150.0
                ),
                AreaModel(id="churrasqueira", nome="Churrasqueira", taxa=80.0),
                AreaModel(id="quadra", nome="Quadra poliesportiva", taxa=0.0),
            ]
        )
        await session.commit()


async def test_concorrencia_duas_reservas_mesma_area_data_grava_apenas_uma() -> None:
    engine = create_db_engine()
    try:
        await init_domain_schema(engine)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        await _prepare_clean_db(session_factory)

        alvo = date(2030, 5, 11)
        start_gate = asyncio.Event()

        async def reservar(apartamento: str):
            async with session_factory() as session:
                await start_gate.wait()
                return await ReservaRepository.criar_atomica(
                    session,
                    apartamento=apartamento,
                    area_id="salao-de-festas",
                    data_reserva=alvo,
                )

        task_101 = asyncio.create_task(reservar("101"))
        task_201 = asyncio.create_task(reservar("201"))
        await asyncio.sleep(0.02)
        start_gate.set()

        r1, r2 = await asyncio.gather(task_101, task_201)
        sucessos = [r for r in (r1, r2) if r.sucesso]
        falhas = [r for r in (r1, r2) if not r.sucesso]

        assert len(sucessos) == 1
        assert len(falhas) == 1
        assert falhas[0].motivo == "data_indisponivel"

        async with session_factory() as session:
            res_101 = await ReservaRepository.listar_ativas_por_apartamento(
                session, "101"
            )
            res_201 = await ReservaRepository.listar_ativas_por_apartamento(
                session, "201"
            )
            assert len(res_101) + len(res_201) == 1
            disponivel = await ReservaRepository.verificar_disponibilidade(
                session, "salao-de-festas", alvo
            )
            assert disponivel is False
    finally:
        await engine.dispose()


async def test_cancelamento_isolado_e_nao_repeticao_de_codigos_cancelados() -> None:
    engine = create_db_engine()
    try:
        await init_domain_schema(engine)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        await _prepare_clean_db(session_factory)

        data_alvo = date(2030, 3, 16)
        async with session_factory() as session:
            criada_302 = await ReservaRepository.criar_atomica(
                session,
                apartamento="302",
                area_id="salao-de-festas",
                data_reserva=data_alvo,
            )
            assert criada_302.sucesso is True
            assert criada_302.codigo is not None

            # Apartamento 101 tenta cancelar a reserva do 302 -> falha sem afetar 302
            tentativa_101 = await ReservaRepository.cancelar_do_apartamento(
                session,
                apartamento="101",
                area_id="salao-de-festas",
                data_reserva=data_alvo,
            )
            assert tentativa_101.sucesso is False
            ativas_302 = await ReservaRepository.listar_ativas_por_apartamento(
                session, "302"
            )
            assert len(ativas_302) == 1
            assert ativas_302[0]["codigo"] == criada_302.codigo

            # Apartamento 302 cancela a própria reserva -> libera data e preserva histórico do código
            cancelada_302 = await ReservaRepository.cancelar_do_apartamento(
                session,
                apartamento="302",
                area_id="salao-de-festas",
                data_reserva=data_alvo,
            )
            assert cancelada_302.sucesso is True
            assert await ReservaRepository.verificar_disponibilidade(
                session, "salao-de-festas", data_alvo
            )

            # Nova reserva na mesma data recebe código inédito != código cancelado
            nova_101 = await ReservaRepository.criar_atomica(
                session,
                apartamento="101",
                area_id="salao-de-festas",
                data_reserva=data_alvo,
            )
            assert nova_101.sucesso is True
            assert nova_101.codigo != criada_302.codigo

            # Visitantes isolados por apartamento
            await VisitanteRepository.autorizar(
                session,
                apartamento="302",
                nome="Marina Duarte",
                data_visita=data_alvo,
            )
            assert (
                await VisitanteRepository.listar_por_apartamento(session, "101")
                == []
            )
            vis_302 = await VisitanteRepository.listar_por_apartamento(
                session, "302"
            )
            assert vis_302 == [{"nome": "Marina Duarte", "data": "2030-03-16"}]
    finally:
        await engine.dispose()
