"""Testes de contrato HTTP das rotas FastAPI do Residencial Aurora (Tarefa 5.2)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from aurora.agents import build_aurora_app, create_session_service
from aurora.config import get_settings
from aurora.db import dispose_engine, get_engine
from aurora.db.seed import restore_initial_data
from aurora.main import create_fastapi_app
from aurora.services import ChatService
from tests.test_chat_service import DeterministicAuroraLlm


@pytest.mark.asyncio
async def test_contrato_http_completo_status_codes_e_schemas() -> None:
    settings = get_settings()
    await restore_initial_data(get_engine(), settings.dados_dir)

    svc = ChatService(
        app=build_aurora_app(model=DeterministicAuroraLlm(), app_name="aurora_api_test"),
        session_service=create_session_service(),
    )
    fastapi_app = create_fastapi_app(chat_service=svc)

    try:
        async with fastapi_app.router.lifespan_context(fastapi_app):
            transport = ASGITransport(app=fastapi_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # 1. Rotas de verificação com dados iniciais
                r_res_101 = await client.get("/apartamentos/101/reservas")
                assert r_res_101.status_code == 200
                assert r_res_101.json() == [
                    {"codigo": "RSV-1377", "area": "quadra", "data": "2030-03-09"}
                ]

                r_vis_302 = await client.get("/apartamentos/302/visitantes")
                assert r_vis_302.status_code == 200
                assert r_vis_302.json() == [
                    {"nome": "Marina Duarte", "data": "2030-03-16"}
                ]

                # 2. Rotas de sessão inexistente -> 404
                assert (await client.get("/sessoes/nao-existe/eventos")).status_code == 404
                assert (
                    await client.post("/sessoes/nao-existe/mensagens", json={"texto": "Oi"})
                ).status_code == 404
                assert (
                    await client.post(
                        "/sessoes/nao-existe/confirmacoes",
                        json={"id": "abc", "confirmado": True},
                    )
                ).status_code == 404

                # 3. Criar sessão -> 201 {"session_id": "..."}
                r_create = await client.post("/sessoes", json={"apartamento": "101"})
                assert r_create.status_code == 201
                body_create = r_create.json()
                assert set(body_create.keys()) == {"session_id"}
                session_id = body_create["session_id"]
                assert isinstance(session_id, str) and len(session_id) > 0

                # 4. Enviar mensagem que gera confirmação -> 200 {"resposta", "confirmacoes_pendentes"}
                r_msg = await client.post(
                    f"/sessoes/{session_id}/mensagens",
                    json={"texto": "Quero reservar o salão de festas para 2030-04-20"},
                )
                assert r_msg.status_code == 200
                body_msg = r_msg.json()
                assert set(body_msg.keys()) == {"resposta", "confirmacoes_pendentes"}
                assert isinstance(body_msg["resposta"], str)
                assert len(body_msg["confirmacoes_pendentes"]) == 1
                pend = body_msg["confirmacoes_pendentes"][0]
                assert set(pend.keys()) == {"id", "acao", "detalhes"}
                assert pend["detalhes"]["area"] == "salao-de-festas"
                assert pend["detalhes"]["data"] == "2030-04-20"

                # 5. Confirmar com id inexistente -> 409
                r_inv = await client.post(
                    f"/sessoes/{session_id}/confirmacoes",
                    json={"id": "id-inexistente", "confirmado": True},
                )
                assert r_inv.status_code == 409

                # 6. Aprovar confirmação pendente -> 200
                r_conf = await client.post(
                    f"/sessoes/{session_id}/confirmacoes",
                    json={"id": pend["id"], "confirmado": True},
                )
                assert r_conf.status_code == 200
                body_conf = r_conf.json()
                assert set(body_conf.keys()) == {"resposta", "confirmacoes_pendentes"}
                assert body_conf["confirmacoes_pendentes"] == []

                # 7. Reenviar mesma confirmação -> 409
                r_dup = await client.post(
                    f"/sessoes/{session_id}/confirmacoes",
                    json={"id": pend["id"], "confirmado": True},
                )
                assert r_dup.status_code == 409

                # 8. Eventos da sessão -> 200 lista ordenada com conteúdo completo
                r_ev = await client.get(f"/sessoes/{session_id}/eventos")
                assert r_ev.status_code == 200
                eventos = r_ev.json()
                assert isinstance(eventos, list)
                assert len(eventos) >= 4
                assert all("id" in ev and "author" in ev for ev in eventos)

                # 9. Rota de verificação reflete reserva aprovada
                r_res_depois = await client.get("/apartamentos/101/reservas")
                assert r_res_depois.status_code == 200
                datas_101 = [item["data"] for item in r_res_depois.json()]
                assert "2030-03-09" in datas_101
                assert "2030-04-20" in datas_101
    finally:
        await svc.close()

    # 10. Novo ciclo de lifespan (reinício sem aurora-reset) preserva dados gravados!
    svc2 = ChatService(
        app=build_aurora_app(model=DeterministicAuroraLlm(), app_name="aurora_api_test"),
        session_service=create_session_service(),
    )
    fastapi_app2 = create_fastapi_app(chat_service=svc2)
    try:
        async with fastapi_app2.router.lifespan_context(fastapi_app2):
            transport2 = ASGITransport(app=fastapi_app2)
            async with AsyncClient(transport=transport2, base_url="http://test") as client2:
                r_res_pos_restart = await client2.get("/apartamentos/101/reservas")
                assert r_res_pos_restart.status_code == 200
                datas_pos = [item["data"] for item in r_res_pos_restart.json()]
                assert "2030-04-20" in datas_pos

                r_ev_pos_restart = await client2.get(f"/sessoes/{session_id}/eventos")
                assert r_ev_pos_restart.status_code == 200
                assert len(r_ev_pos_restart.json()) == len(eventos)
    finally:
        await svc2.close()
        await restore_initial_data(get_engine(), settings.dados_dir)
        await dispose_engine()
