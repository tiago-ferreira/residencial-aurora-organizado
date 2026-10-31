"""Exportação consolidada das tools do Google ADK."""

from aurora.tools.regulamento_tools import (
    buscar_capitulo_regulamento,
    ler_secao_regulamento,
)
from aurora.tools.reservas_tools import (
    cancelar_minha_reserva,
    consultar_disponibilidade_area,
    criar_reserva,
    extrair_apartamento_da_sessao,
    listar_areas_comuns,
    listar_minhas_reservas,
    normalizar_area_id,
)
from aurora.tools.visitantes_tools import (
    autorizar_visitante,
    listar_meus_visitantes,
)

ALL_AGENT_TOOLS = (
    listar_areas_comuns,
    listar_minhas_reservas,
    consultar_disponibilidade_area,
    criar_reserva,
    cancelar_minha_reserva,
    listar_meus_visitantes,
    autorizar_visitante,
    buscar_capitulo_regulamento,
    ler_secao_regulamento,
)

__all__ = [
    "ALL_AGENT_TOOLS",
    "autorizar_visitante",
    "buscar_capitulo_regulamento",
    "cancelar_minha_reserva",
    "consultar_disponibilidade_area",
    "criar_reserva",
    "extrair_apartamento_da_sessao",
    "ler_secao_regulamento",
    "listar_areas_comuns",
    "listar_meus_visitantes",
    "listar_minhas_reservas",
    "normalizar_area_id",
]
