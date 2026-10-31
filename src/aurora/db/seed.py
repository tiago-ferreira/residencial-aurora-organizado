"""Rotinas de carga inicial (seed) e restauração a partir de dados/*.json."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from sqlalchemy import delete, exists, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from aurora.db.models import (
    ApartamentoModel,
    AreaModel,
    ConfirmacaoPendenteModel,
    ReservaModel,
    VisitanteModel,
    init_domain_schema,
)

_ADK_TABLES = ("events", "sessions", "user_states", "app_states")


def _load_json(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def _compute_next_seq_start(reservas_raw: list[dict]) -> int:
    max_num = 4999
    for item in reservas_raw:
        match = re.search(r"(\d+)$", str(item.get("codigo", "")))
        if match:
            max_num = max(max_num, int(match.group(1)))
    return max_num + 1


async def restore_initial_data(
    engine: AsyncEngine,
    dados_dir: Path,
    *,
    clear_adk_sessions: bool = True,
) -> None:
    """Restaura o banco de dados ao estado exato dos arquivos em dados/ (somente leitura)."""
    await init_domain_schema(engine)

    apartamentos_raw = _load_json(dados_dir / "apartamentos.json")
    areas_raw = _load_json(dados_dir / "areas.json")
    reservas_raw = _load_json(dados_dir / "reservas.json")
    visitantes_raw = _load_json(dados_dir / "visitantes.json")
    next_seq = _compute_next_seq_start(reservas_raw)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        await session.execute(delete(ConfirmacaoPendenteModel))
        await session.execute(delete(VisitanteModel))
        await session.execute(delete(ReservaModel))
        await session.execute(delete(AreaModel))
        await session.execute(delete(ApartamentoModel))

        if clear_adk_sessions:
            existing_tables_rows = await session.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                )
            )
            existing_tables = {r[0] for r in existing_tables_rows.fetchall()}
            for table_name in _ADK_TABLES:
                if table_name in existing_tables:
                    await session.execute(text(f'DELETE FROM "{table_name}"'))

        session.add_all(
            [
                ApartamentoModel(
                    numero=str(item["numero"]),
                    morador=str(item["morador"]),
                )
                for item in apartamentos_raw
            ]
        )
        session.add_all(
            [
                AreaModel(
                    id=str(item["id"]),
                    nome=str(item["nome"]),
                    taxa=float(item["taxa"]),
                )
                for item in areas_raw
            ]
        )
        await session.flush()

        session.add_all(
            [
                ReservaModel(
                    codigo=str(item["codigo"]),
                    apartamento=str(item["apartamento"]),
                    area_id=str(item["area"]),
                    data=date.fromisoformat(str(item["data"])),
                    ativa=True,
                )
                for item in reservas_raw
            ]
        )
        session.add_all(
            [
                VisitanteModel(
                    apartamento=str(item["apartamento"]),
                    nome=str(item["nome"]),
                    data=date.fromisoformat(str(item["data"])),
                )
                for item in visitantes_raw
            ]
        )

        await session.execute(
            text("SELECT setval('reserva_codigo_seq', :val, false)"),
            {"val": next_seq},
        )
        await session.commit()


async def ensure_seeded_if_empty(
    engine: AsyncEngine,
    dados_dir: Path,
) -> bool:
    """Inicializa schema e popula dados iniciais apenas se o banco estiver vazio."""
    await init_domain_schema(engine)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        has_areas = bool(
            await session.scalar(select(exists(select(1).select_from(AreaModel))))
        )
    if not has_areas:
        await restore_initial_data(
            engine,
            dados_dir,
            clear_adk_sessions=False,
        )
        return True
    return False
