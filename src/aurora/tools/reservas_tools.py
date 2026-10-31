"""Tools operacionais de áreas comuns e reservas com isolamento por sessão (Garantias 1, 2 e 5)."""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any

from google.adk.tools import ToolContext

from aurora.db import AreaRepository, ReservaRepository, get_session_factory

_AREA_ALIASES: dict[str, str] = {
    "salao": "salao-de-festas",
    "salao-de-festas": "salao-de-festas",
    "salao-de-festa": "salao-de-festas",
    "salao-festas": "salao-de-festas",
    "churrasqueira": "churrasqueira",
    "churrasco": "churrasqueira",
    "quadra": "quadra",
    "quadra-poliesportiva": "quadra",
    "quadra-esportiva": "quadra",
}


def normalizar_area_id(area: str) -> str:
    """Normaliza nomes informais de áreas comuns para o id oficial do cadastro."""
    sem_acentos = "".join(
        ch
        for ch in unicodedata.normalize("NFD", area.strip().lower())
        if unicodedata.category(ch) != "Mn"
    )
    slug = re.sub(r"[^a-z0-9]+", "-", sem_acentos).strip("-")
    return _AREA_ALIASES.get(slug, slug)


def extrair_apartamento_da_sessao(tool_context: ToolContext) -> str:
    """Extrai o apartamento autenticado exclusivamente do state da sessão (Garantia 2)."""
    apartamento = tool_context.state.get("apartamento")
    if apartamento is None or not str(apartamento).strip():
        raise ValueError("Apartamento não encontrado no state da sessão.")
    return str(apartamento).strip()


async def listar_areas_comuns() -> dict[str, Any]:
    """Lista as áreas comuns disponíveis para reserva e o valor de suas taxas em reais."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        areas = await AreaRepository.listar_areas(session)
    return {"areas": areas}


async def listar_minhas_reservas(*, tool_context: ToolContext) -> dict[str, Any]:
    """Lista todas as reservas ativas pertencentes exclusivamente ao apartamento da sessão atual."""
    apartamento = extrair_apartamento_da_sessao(tool_context)
    session_factory = get_session_factory()
    async with session_factory() as session:
        reservas = await ReservaRepository.listar_ativas_por_apartamento(
            session, apartamento
        )
    return {"apartamento": apartamento, "reservas": reservas}


async def consultar_disponibilidade_area(
    area: str,
    data: str,
    *,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Verifica se uma área comum está livre ou ocupada numa data (AAAA-MM-DD).

    Retorna apenas se a data está disponível ou ocupada, sem expor dados de outros apartamentos.
    """
    _ = extrair_apartamento_da_sessao(tool_context)
    area_id = normalizar_area_id(area)
    try:
        data_reserva = date.fromisoformat(data.strip())
    except ValueError:
        return {
            "sucesso": False,
            "motivo": "Formato de data inválido. Use AAAA-MM-DD.",
        }

    session_factory = get_session_factory()
    async with session_factory() as session:
        area_obj = await AreaRepository.obter_area(session, area_id)
        if area_obj is None:
            return {
                "sucesso": False,
                "motivo": "Área comum não encontrada.",
            }
        disponivel = await ReservaRepository.verificar_disponibilidade(
            session, area_id, data_reserva
        )

    return {
        "area": area_id,
        "data": data_reserva.isoformat(),
        "taxa": float(area_obj.taxa),
        "disponivel": disponivel,
    }


async def criar_reserva(
    area: str,
    data: str,
    *,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Cria uma reserva de área comum para o apartamento da sessão na data informada (AAAA-MM-DD).

    Áreas com taxa maior que zero exigem confirmação do sistema antes da gravação.
    Áreas com taxa zero são gravadas imediatamente sem confirmação.
    """
    apartamento = extrair_apartamento_da_sessao(tool_context)
    area_id = normalizar_area_id(area)
    try:
        data_reserva = date.fromisoformat(data.strip())
    except ValueError:
        return {
            "sucesso": False,
            "motivo": "Formato de data inválido. Use AAAA-MM-DD.",
        }

    data_iso = data_reserva.isoformat()
    session_factory = get_session_factory()

    async with session_factory() as session:
        area_obj = await AreaRepository.obter_area(session, area_id)
        if area_obj is None:
            return {
                "sucesso": False,
                "motivo": "Área comum não encontrada.",
            }

        taxa = float(area_obj.taxa)

        if taxa > 0:
            confirmation = tool_context.tool_confirmation
            if confirmation is None:
                disponivel = await ReservaRepository.verificar_disponibilidade(
                    session, area_id, data_reserva
                )
                if not disponivel:
                    return {
                        "sucesso": False,
                        "area": area_id,
                        "data": data_iso,
                        "motivo": "A área já está ocupada nesta data.",
                    }

                detalhes = {
                    "area": area_id,
                    "data": data_iso,
                    "taxa": taxa,
                }
                tool_context.request_confirmation(
                    hint=(
                        f"Confirma a reserva de {area_obj.nome} para {data_iso} "
                        f"com cobrança de taxa de R$ {taxa:.2f}?"
                    ),
                    payload={
                        "acao": "reservar_area_comum",
                        "detalhes": detalhes,
                    },
                )
                tool_context.actions.skip_summarization = True
                return {
                    "status": "aguardando_confirmacao",
                    "acao": "reservar_area_comum",
                    "detalhes": detalhes,
                }

            if not confirmation.confirmed:
                return {
                    "sucesso": False,
                    "status": "confirmacao_negada",
                    "area": area_id,
                    "data": data_iso,
                    "mensagem": "A reserva foi negada pelo morador e nada foi gravado.",
                }

        resultado = await ReservaRepository.criar_atomica(
            session,
            apartamento=apartamento,
            area_id=area_id,
            data_reserva=data_reserva,
        )

    if not resultado.sucesso:
        return {
            "sucesso": False,
            "area": area_id,
            "data": data_iso,
            "motivo": "A área já está ocupada nesta data.",
        }

    return {
        "sucesso": True,
        "codigo": resultado.codigo,
        "area": area_id,
        "data": data_iso,
        "taxa": taxa,
    }


async def cancelar_minha_reserva(
    area: str = "",
    data: str = "",
    codigo: str = "",
    *,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Cancela imediatamente (sem pedir confirmação) uma reserva ativa do próprio apartamento da sessão.

    Pode localizar a reserva pela combinação de area + data (AAAA-MM-DD) ou pelo codigo da reserva.
    """
    apartamento = extrair_apartamento_da_sessao(tool_context)
    area_id = normalizar_area_id(area) if area.strip() else None
    codigo_limpo = codigo.strip().upper() if codigo.strip() else None

    data_reserva: date | None = None
    if data.strip():
        try:
            data_reserva = date.fromisoformat(data.strip())
        except ValueError:
            return {
                "sucesso": False,
                "motivo": "Formato de data inválido. Use AAAA-MM-DD.",
            }

    if not codigo_limpo and not (area_id and data_reserva):
        return {
            "sucesso": False,
            "motivo": "Informe o código da reserva ou a área comum junto com a data (AAAA-MM-DD).",
        }

    session_factory = get_session_factory()
    async with session_factory() as session:
        resultado = await ReservaRepository.cancelar_do_apartamento(
            session,
            apartamento=apartamento,
            area_id=area_id,
            data_reserva=data_reserva,
            codigo=codigo_limpo,
        )

    if not resultado.sucesso:
        return {
            "sucesso": False,
            "motivo": "Nenhuma reserva ativa encontrada para o seu apartamento com os dados informados.",
        }

    return {
        "sucesso": True,
        "codigo": resultado.codigo,
        "area": resultado.area,
        "data": resultado.data,
    }
