"""Testes unitários do indexador e das tools seletivas do regulamento (Garantia 4)."""

from __future__ import annotations

import json

from aurora.services.regulamento_index import get_regulamento_index
from aurora.tools.regulamento_tools import (
    buscar_capitulo_regulamento,
    ler_secao_regulamento,
)


def test_indexa_todos_os_14_capitulos_do_regulamento() -> None:
    index = get_regulamento_index()
    assert len(index.secoes) == 14


def test_busca_horario_piscina_domingo_retorna_apenas_capitulo_piscina() -> None:
    resultado = buscar_capitulo_regulamento(
        "Até que horas a piscina funciona aos domingos?"
    )
    assert resultado["encontrado"] is True
    assert resultado["secao_id"] == "capitulo-iv-piscina"
    assert "Capítulo IV: Piscina" in resultado["titulo"]
    assert "Aos domingos e feriados, a piscina funciona das 9h às 20h." in resultado["conteudo"]

    serializado = json.dumps(resultado, ensure_ascii=False)
    # Garante ausência absoluta de trechos/artigos de outros capítulos
    assert "Capítulo I:" not in serializado
    assert "Capítulo III:" not in serializado
    assert "Capítulo V:" not in serializado
    assert "Capítulo VI:" not in serializado
    assert "Capítulo VIII:" not in serializado
    assert "coleira refletiva cor de mostarda" not in serializado
    assert "plástico bolha lilás" not in serializado
    assert "lona xadrez vermelha" not in serializado


def test_ler_secao_por_id_e_fallback_sem_vazar_corpos() -> None:
    cap_mudancas = ler_secao_regulamento("capitulo-ix-mudancas")
    assert cap_mudancas["encontrado"] is True
    assert "Capítulo IX: Mudanças" in cap_mudancas["titulo"]
    assert "Capítulo IV: Piscina" not in cap_mudancas["conteudo"]

    sem_match = buscar_capitulo_regulamento("xyztermoinexistente123")
    assert sem_match["encontrado"] is False
    assert "conteudo" not in sem_match
    assert len(sem_match["secoes_disponiveis"]) == 14
