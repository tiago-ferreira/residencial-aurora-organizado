"""Tools enxutas para consulta seletiva ao regulamento interno (Garantia 4)."""

from __future__ import annotations

from typing import Any

from aurora.services.regulamento_index import get_regulamento_index


def buscar_capitulo_regulamento(consulta: str) -> dict[str, Any]:
    """Busca no regulamento interno apenas o capítulo pertinente ao assunto perguntado.

    Args:
        consulta: Termos ou pergunta sobre a regra do condomínio (ex.: 'piscina domingo').

    Returns:
        Dicionário contendo somente o capítulo mais relevante ou a lista de títulos disponíveis.
    """
    return get_regulamento_index().buscar_capitulo(consulta)


def ler_secao_regulamento(secao_id: str) -> dict[str, Any]:
    """Lê um capítulo específico do regulamento pelo seu identificador de seção.

    Args:
        secao_id: Identificador do capítulo retornado em secoes_disponiveis (ex.: 'capitulo-iv-piscina').

    Returns:
        Dicionário contendo exclusivamente o conteúdo do capítulo solicitado.
    """
    return get_regulamento_index().ler_secao(secao_id)
