""" Ponto de entrada CLI para restaurar o estado inicial do condomínio."""

from __future__ import annotations

import asyncio

from aurora.config import get_settings
from aurora.db.engine import create_db_engine
from aurora.db.seed import restore_initial_data


async def _run_restore() -> None:
    settings = get_settings()
    engine = create_db_engine(settings.database_url)
    try:
        await restore_initial_data(
            engine,
            settings.dados_dir,
            clear_adk_sessions=True,
        )
    finally:
        await engine.dispose()


def main() -> None:
    """Restaura reservas, visitantes e sessões para o estado inicial de dados/."""
    asyncio.run(_run_restore())
    print("Dados do Residencial Aurora restaurados com sucesso.")


if __name__ == "__main__":
    main()
