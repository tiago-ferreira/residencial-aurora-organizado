"""Testes da topologia multiagente, ResumabilityConfig e DatabaseSessionService (Tarefa 4.2)."""

from __future__ import annotations

import uuid

import pytest

from aurora.agents import (
    aurora_app,
    create_runner,
    create_session_service,
    regulamento_agent,
    reservas_agent,
    root_agent,
    visitantes_agent,
)
from aurora.config import get_settings


def test_app_topologia_multiagente_e_resumability() -> None:
    assert aurora_app.root_agent is root_agent
    assert aurora_app.resumability_config is not None
    assert aurora_app.resumability_config.is_resumable is True

    assert len(root_agent.sub_agents) >= 2
    sub_names = [agent.name for agent in root_agent.sub_agents]
    assert sub_names == ["reservas_agent", "visitantes_agent", "regulamento_agent"]

    for agent in [root_agent, reservas_agent, visitantes_agent, regulamento_agent]:
        assert agent is not None
        assert agent.mode == "chat"
        assert agent.disallow_transfer_to_parent is False
        assert agent.disallow_transfer_to_peers is False


def test_instrucoes_nao_incluem_texto_do_regulamento() -> None:
    regulamento_path = get_settings().dados_dir / "regulamento.md"
    regulamento_texto = regulamento_path.read_text(encoding="utf-8")

    linhas_significativas = [
        linha.strip()
        for linha in regulamento_texto.splitlines()
        if len(linha.strip()) > 25
    ]
    assert len(linhas_significativas) >= 10

    for agent in [root_agent, reservas_agent, visitantes_agent, regulamento_agent]:
        assert isinstance(agent.instruction, str)
        assert "## Capítulo" not in agent.instruction
        assert "coleira refletiva cor de mostarda" not in agent.instruction
        assert "plástico bolha lilás" not in agent.instruction
        assert "lona xadrez vermelha" not in agent.instruction
        for linha in linhas_significativas:
            assert linha not in agent.instruction


@pytest.mark.asyncio
async def test_database_session_service_e_runner_conectados_ao_postgres() -> None:
    session_service = create_session_service()
    try:
        runner = create_runner(session_service=session_service)
        assert runner.app_name == aurora_app.name
        assert runner.resumability_config is not None
        assert runner.resumability_config.is_resumable is True

        sid = f"test-session-{uuid.uuid4().hex}"
        created = await session_service.create_session(
            app_name=aurora_app.name,
            user_id="morador",
            session_id=sid,
            state={"apartamento": "101"},
        )
        assert created.id == sid
        assert created.state["apartamento"] == "101"

        reloaded = await session_service.get_session(
            app_name=aurora_app.name,
            user_id="morador",
            session_id=sid,
        )
        assert reloaded is not None
        assert reloaded.state["apartamento"] == "101"

        await session_service.delete_session(
            app_name=aurora_app.name,
            user_id="morador",
            session_id=sid,
        )
    finally:
        await session_service.close()
