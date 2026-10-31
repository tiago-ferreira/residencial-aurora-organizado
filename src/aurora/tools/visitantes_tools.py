"""Tools operacionais de visitantes com isolamento por sessão e confirmação obrigatória (Garantias 1 e 2)."""

from __future__ import annotations

from datetime import date
from typing import Any

from google.adk.tools import ToolContext

from aurora.db import VisitanteRepository, get_session_factory
from aurora.tools.reservas_tools import extrair_apartamento_da_sessao


async def listar_meus_visitantes(*, tool_context: ToolContext) -> dict[str, Any]:
    """Lista os visitantes autorizados exclusivamente para o apartamento da sessão atual."""
    apartamento = extrair_apartamento_da_sessao(tool_context)
    session_factory = get_session_factory()
    async with session_factory() as session:
        visitantes = await VisitanteRepository.listar_por_apartamento(
            session, apartamento
        )
    return {"apartamento": apartamento, "visitantes": visitantes}


async def autorizar_visitante(
    nome: str,
    data: str,
    *,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Solicita autorização de entrada para um visitante na data informada (AAAA-MM-DD).

    Toda autorização de visitante libera acesso ao condomínio e exige confirmação pelo sistema,
    independentemente do que o morador escrever na conversa.
    """
    apartamento = extrair_apartamento_da_sessao(tool_context)
    nome_limpo = nome.strip()
    if not nome_limpo:
        return {
            "sucesso": False,
            "motivo": "O nome do visitante é obrigatório.",
        }

    try:
        data_visita = date.fromisoformat(data.strip())
    except ValueError:
        return {
            "sucesso": False,
            "motivo": "Formato de data inválido. Use AAAA-MM-DD.",
        }

    data_iso = data_visita.isoformat()
    confirmation = tool_context.tool_confirmation

    if confirmation is None:
        detalhes = {
            "nome": nome_limpo,
            "data": data_iso,
        }
        tool_context.request_confirmation(
            hint=f"Confirma a liberação de entrada para {nome_limpo} em {data_iso}?",
            payload={
                "acao": "autorizar_visitante",
                "detalhes": detalhes,
            },
        )
        tool_context.actions.skip_summarization = True
        return {
            "status": "aguardando_confirmacao",
            "acao": "autorizar_visitante",
            "detalhes": detalhes,
        }

    if not confirmation.confirmed:
        return {
            "sucesso": False,
            "status": "confirmacao_negada",
            "nome": nome_limpo,
            "data": data_iso,
            "mensagem": "A autorização do visitante foi negada pelo morador e nada foi registrado.",
        }

    session_factory = get_session_factory()
    async with session_factory() as session:
        visitante = await VisitanteRepository.autorizar(
            session,
            apartamento=apartamento,
            nome=nome_limpo,
            data_visita=data_visita,
        )

    return {
        "sucesso": True,
        "visitante": visitante,
    }
