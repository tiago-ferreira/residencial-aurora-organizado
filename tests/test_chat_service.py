"""Testes integrados do ChatService com PostgreSQL e retomada de confirmações ADK (Tarefa 5.1)."""

from __future__ import annotations

import uuid
from typing import AsyncGenerator

import pytest
from google.adk.models.base_llm import BaseLlm, LlmCapabilities
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from aurora.agents import build_aurora_app, create_session_service
from aurora.config import get_settings
from aurora.db import ReservaRepository, get_engine, get_session_factory
from aurora.db.seed import restore_initial_data
from aurora.services import (
    ChatService,
    ConfirmationConflictError,
    SessionNotFoundError,
)


class DeterministicAuroraLlm(BaseLlm):
    """Modelo determinístico para exercitar transferências, tools e confirmações reais do ADK."""

    model: str = "deterministic-aurora-test"

    @property
    def capabilities(self) -> LlmCapabilities:
        return LlmCapabilities(output_schema_and_tools=True)

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        tools = llm_request.tools_dict or {}
        last_content = llm_request.contents[-1] if llm_request.contents else None

        # Se o último turno do histórico já é o resultado da execução da tool (pós-confirmação ou direta)
        if last_content and last_content.parts:
            fr_parts = [
                p.function_response
                for p in last_content.parts
                if p.function_response is not None
            ]
            for fr in fr_parts:
                if fr.name in ("criar_reserva", "autorizar_visitante", "cancelar_minha_reserva"):
                    resp_data = fr.response or {}
                    if resp_data.get("sucesso") is True:
                        codigo = resp_data.get("codigo", "")
                        yield LlmResponse(
                            partial=False,
                            content=types.Content(
                                role="model",
                                parts=[
                                    types.Part.from_text(
                                        text=f"Operação concluída com sucesso. {codigo}".strip()
                                    )
                                ],
                            ),
                        )
                        return
                    if resp_data.get("status") == "confirmacao_negada":
                        yield LlmResponse(
                            partial=False,
                            content=types.Content(
                                role="model",
                                parts=[
                                    types.Part.from_text(
                                        text="Entendido, a solicitação foi cancelada e nada foi gravado."
                                    )
                                ],
                            ),
                        )
                        return
                    yield LlmResponse(
                        partial=False,
                        content=types.Content(
                            role="model",
                            parts=[
                                types.Part.from_text(
                                    text=str(resp_data.get("motivo") or "Não foi possível concluir.")
                                )
                            ],
                        ),
                    )
                    return

        # Extrair último texto real enviado pelo morador (ignorando citações internas de outros agentes)
        user_text = ""
        for content in reversed(llm_request.contents or []):
            if content.role == "user" and content.parts:
                texts = [
                    p.text
                    for p in content.parts
                    if p.text
                    and not p.text.startswith("For context:")
                    and "<<<BEGIN_QUOTED_AGENT_CONTENT>>>" not in p.text
                ]
                if texts:
                    user_text = " ".join(texts).lower()
                    break

        # Se estamos no root_agent (sem criar_reserva nas tools), transfere para reservas_agent
        if "criar_reserva" not in tools and "transfer_to_agent" in tools:
            fc = types.FunctionCall(
                id=f"fc-transfer-{uuid.uuid4().hex[:8]}",
                name="transfer_to_agent",
                args={"agent_name": "reservas_agent"},
            )
            yield LlmResponse(
                partial=False,
                content=types.Content(
                    role="model",
                    parts=[types.Part(function_call=fc)],
                ),
            )
            return

        # No reservas_agent: dispara criar_reserva para o salão de festas em 2030-04-20
        if "salão" in user_text or "salao" in user_text:
            fc = types.FunctionCall(
                id=f"fc-reserva-{uuid.uuid4().hex[:8]}",
                name="criar_reserva",
                args={"area": "salao-de-festas", "data": "2030-04-20"},
            )
            yield LlmResponse(
                partial=False,
                content=types.Content(
                    role="model",
                    parts=[types.Part(function_call=fc)],
                ),
            )
            return

        yield LlmResponse(
            partial=False,
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text="Olá, como posso ajudar?")],
            ),
        )


@pytest.mark.asyncio
async def test_chat_service_fluxo_confirmacao_retomada_pos_reinicio_e_conflitos() -> None:
    settings = get_settings()
    engine = get_engine()
    await restore_initial_data(engine, settings.dados_dir)

    llm = DeterministicAuroraLlm()
    app1 = build_aurora_app(model=llm, app_name="aurora_test_chat")
    svc1 = ChatService(app=app1, session_service=create_session_service())

    try:
        # 1. Sessão inexistente levanta SessionNotFoundError (404)
        with pytest.raises(SessionNotFoundError):
            await svc1.listar_eventos("sessao-inexistente")
        with pytest.raises(SessionNotFoundError):
            await svc1.enviar_mensagem("sessao-inexistente", "Oi")
        with pytest.raises(SessionNotFoundError):
            await svc1.responder_confirmacao("sessao-inexistente", "qualquer", True)

        # 2. Cria sessão para 101 e outra para 201
        s1 = await svc1.criar_sessao("101")
        s2 = await svc1.criar_sessao("201")
        assert s1 and s2 and s1 != s2

        # 3. Pede reserva paga (salão de festas em 2030-04-20) -> gera confirmação pendente sem gravar
        r_ped1 = await svc1.enviar_mensagem(
            s1, "Reserve o salão de festas para 2030-04-20."
        )
        assert len(r_ped1["confirmacoes_pendentes"]) == 1
        conf1 = r_ped1["confirmacoes_pendentes"][0]
        assert conf1["acao"] == "reservar_area_comum"
        assert conf1["detalhes"]["area"] == "salao-de-festas"
        assert conf1["detalhes"]["data"] == "2030-04-20"

        async with get_session_factory()() as db:
            reservas_101 = await ReservaRepository.listar_ativas_por_apartamento(db, "101")
        assert not any(r["data"] == "2030-04-20" for r in reservas_101)

        # 4. Outra sessão (s2) tentando responder confirmação de s1 -> 409
        with pytest.raises(ConfirmationConflictError):
            await svc1.responder_confirmacao(s2, conf1["id"], True)

        # 5. Nega a confirmação -> nada gravado e sem pendências
        r_neg = await svc1.responder_confirmacao(s1, conf1["id"], False)
        assert r_neg["confirmacoes_pendentes"] == []
        async with get_session_factory()() as db:
            reservas_101 = await ReservaRepository.listar_ativas_por_apartamento(db, "101")
        assert not any(r["data"] == "2030-04-20" for r in reservas_101)

        # 6. Repete o pedido -> gera nova confirmação pendente
        r_ped2 = await svc1.enviar_mensagem(
            s1, "Reserve o salão de festas para 2030-04-20."
        )
        assert len(r_ped2["confirmacoes_pendentes"]) == 1
        conf2 = r_ped2["confirmacoes_pendentes"][0]
        assert conf2["id"] != conf1["id"]
    finally:
        await svc1.close()

    # 7. Simula reinício do processo da API: nova instância de App, DatabaseSessionService e Runner!
    app2 = build_aurora_app(model=DeterministicAuroraLlm(), app_name="aurora_test_chat")
    svc2 = ChatService(app=app2, session_service=create_session_service())
    try:
        r_apr = await svc2.responder_confirmacao(s1, conf2["id"], True)
        assert r_apr["confirmacoes_pendentes"] == []
        assert "RSV-" in r_apr["resposta"]

        async with get_session_factory()() as db:
            reservas_101 = await ReservaRepository.listar_ativas_por_apartamento(db, "101")
        salao_20 = [
            r for r in reservas_101
            if r["area"] == "salao-de-festas" and r["data"] == "2030-04-20"
        ]
        assert len(salao_20) == 1

        # 8. Reenviar o mesmo id já respondido -> ConfirmationConflictError (409) e continua 1 reserva
        with pytest.raises(ConfirmationConflictError):
            await svc2.responder_confirmacao(s1, conf2["id"], True)

        # 9. Enviar id inexistente -> ConfirmationConflictError (409)
        with pytest.raises(ConfirmationConflictError):
            await svc2.responder_confirmacao(s1, "id-inexistente", True)

        async with get_session_factory()() as db:
            reservas_101_depois = await ReservaRepository.listar_ativas_por_apartamento(db, "101")
        salao_20_depois = [
            r for r in reservas_101_depois
            if r["area"] == "salao-de-festas" and r["data"] == "2030-04-20"
        ]
        assert len(salao_20_depois) == 1

        # 10. Eventos completos em ordem cronológica
        eventos = await svc2.listar_eventos(s1)
        assert len(eventos) >= 6
    finally:
        await svc2.close()
        await restore_initial_data(engine, settings.dados_dir)
