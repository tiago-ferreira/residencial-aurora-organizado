"""Testes das tools operacionais de reservas e visitantes (Garantias 1 e 2)."""

from __future__ import annotations

import inspect
import json
from typing import Any

from google.adk.events.event_actions import EventActions
from google.adk.tools.tool_confirmation import ToolConfirmation

from aurora.config import get_settings
from aurora.db import dispose_engine, get_engine, restore_initial_data
from aurora.tools import (
    ALL_AGENT_TOOLS,
    autorizar_visitante,
    cancelar_minha_reserva,
    consultar_disponibilidade_area,
    criar_reserva,
    listar_meus_visitantes,
    listar_minhas_reservas,
)


class FakeToolContext:
    """Stub leve compatível com a interface de ToolContext usada pelas tools."""

    def __init__(
        self,
        apartamento: str,
        *,
        function_call_id: str = "fc-test-1",
        tool_confirmation: ToolConfirmation | None = None,
    ) -> None:
        self.state: dict[str, Any] = {"apartamento": apartamento}
        self.function_call_id = function_call_id
        self.tool_confirmation = tool_confirmation
        self.actions = EventActions()

    def request_confirmation(
        self, *, hint: str | None = None, payload: Any | None = None
    ) -> None:
        self.actions.requested_tool_confirmations[self.function_call_id] = (
            ToolConfirmation(hint=hint or "", payload=payload)
        )


def test_nenhuma_tool_aceita_parametro_apartamento_do_modelo() -> None:
    for fn in ALL_AGENT_TOOLS:
        sig = inspect.signature(fn)
        assert "apartamento" not in sig.parameters, (
            f"Tool {fn.__name__} não pode expor parâmetro 'apartamento' ao modelo."
        )


async def test_isolamento_de_apartamento_e_fluxo_confirmacao_nas_tools() -> None:
    settings = get_settings()
    await dispose_engine()
    engine = get_engine()
    try:
        await restore_initial_data(engine, settings.dados_dir)

        ctx_101 = FakeToolContext("101")

        # 1. Sessão do 101 não enxerga reservas nem visitantes do 302
        minhas_res = await listar_minhas_reservas(tool_context=ctx_101)  # type: ignore[arg-type]
        assert minhas_res["reservas"] == [
            {"codigo": "RSV-1377", "area": "quadra", "data": "2030-03-09"}
        ]
        assert "RSV-4821" not in json.dumps(minhas_res)

        meus_vis = await listar_meus_visitantes(tool_context=ctx_101)  # type: ignore[arg-type]
        assert meus_vis["visitantes"] == []
        assert "Marina Duarte" not in json.dumps(meus_vis)

        # 2. Disponibilidade em data ocupada pelo 302 não vaza RSV-4821 nem 302
        disp = await consultar_disponibilidade_area(
            "salão de festas",
            "2030-03-16",
            tool_context=ctx_101,  # type: ignore[arg-type]
        )
        assert disp["disponivel"] is False
        disp_str = json.dumps(disp)
        assert "RSV-4821" not in disp_str
        assert "302" not in disp_str

        # 3. Cancelar reserva do 302 a partir do 101 falha sem vazar RSV-4821
        canc_302 = await cancelar_minha_reserva(
            area="salão de festas",
            data="2030-03-16",
            tool_context=ctx_101,  # type: ignore[arg-type]
        )
        assert canc_302["sucesso"] is False
        assert "RSV-4821" not in json.dumps(canc_302)

        # 4. Cancelar própria reserva executa direto sem pedir confirmação
        ctx_canc = FakeToolContext("101")
        canc_101 = await cancelar_minha_reserva(
            area="quadra",
            data="2030-03-09",
            tool_context=ctx_canc,  # type: ignore[arg-type]
        )
        assert canc_101["sucesso"] is True
        assert ctx_canc.actions.requested_tool_confirmations == {}

        # 5. Área gratuita (quadra, taxa 0) grava direto sem pedir confirmação
        ctx_quadra = FakeToolContext("101")
        res_quadra = await criar_reserva(
            "quadra",
            "2030-04-06",
            tool_context=ctx_quadra,  # type: ignore[arg-type]
        )
        assert res_quadra["sucesso"] is True
        assert ctx_quadra.actions.requested_tool_confirmations == {}

        # 6. Área paga (salao-de-festas) pede confirmação quando None, nega em False, grava em True
        ctx_salao_pendente = FakeToolContext("101", function_call_id="fc-salao")
        res_pendente = await criar_reserva(
            "salão de festas",
            "2030-04-20",
            tool_context=ctx_salao_pendente,  # type: ignore[arg-type]
        )
        assert res_pendente["status"] == "aguardando_confirmacao"
        assert "fc-salao" in ctx_salao_pendente.actions.requested_tool_confirmations
        payload = ctx_salao_pendente.actions.requested_tool_confirmations[
            "fc-salao"
        ].payload
        assert payload["detalhes"]["area"] == "salao-de-festas"
        assert payload["detalhes"]["data"] == "2030-04-20"

        ctx_salao_negado = FakeToolContext(
            "101", tool_confirmation=ToolConfirmation(confirmed=False)
        )
        res_negado = await criar_reserva(
            "salão de festas",
            "2030-04-20",
            tool_context=ctx_salao_negado,  # type: ignore[arg-type]
        )
        assert res_negado["sucesso"] is False

        ctx_salao_aprovado = FakeToolContext(
            "101", tool_confirmation=ToolConfirmation(confirmed=True)
        )
        res_aprovado = await criar_reserva(
            "salão de festas",
            "2030-04-20",
            tool_context=ctx_salao_aprovado,  # type: ignore[arg-type]
        )
        assert res_aprovado["sucesso"] is True

        # 7. Visitante exige confirmação (None -> pendente, False -> negado, True -> gravado)
        ctx_vis_pend = FakeToolContext("101", function_call_id="fc-vis")
        vis_pend = await autorizar_visitante(
            "Joana Ribeiro",
            "2030-04-21",
            tool_context=ctx_vis_pend,  # type: ignore[arg-type]
        )
        assert vis_pend["status"] == "aguardando_confirmacao"
        vis_payload = ctx_vis_pend.actions.requested_tool_confirmations[
            "fc-vis"
        ].payload
        assert vis_payload["detalhes"] == {
            "nome": "Joana Ribeiro",
            "data": "2030-04-21",
        }

        ctx_vis_neg = FakeToolContext(
            "101", tool_confirmation=ToolConfirmation(confirmed=False)
        )
        vis_neg = await autorizar_visitante(
            "Joana Ribeiro",
            "2030-04-21",
            tool_context=ctx_vis_neg,  # type: ignore[arg-type]
        )
        assert vis_neg["sucesso"] is False

        ctx_vis_ok = FakeToolContext(
            "101", tool_confirmation=ToolConfirmation(confirmed=True)
        )
        vis_ok = await autorizar_visitante(
            "Joana Ribeiro",
            "2030-04-21",
            tool_context=ctx_vis_ok,  # type: ignore[arg-type]
        )
        assert vis_ok["sucesso"] is True

        meus_vis_finais = await listar_meus_visitantes(tool_context=ctx_101)  # type: ignore[arg-type]
        assert meus_vis_finais["visitantes"] == [
            {"nome": "Joana Ribeiro", "data": "2030-04-21"}
        ]
    finally:
        await dispose_engine()
