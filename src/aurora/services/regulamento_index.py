"""Indexador léxico por capítulos para consulta seletiva de dados/regulamento.md."""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from aurora.config import get_settings

_PT_STOPWORDS = frozenset(
    {
        "a",
        "ao",
        "aos",
        "aquela",
        "aquele",
        "as",
        "ate",
        "com",
        "como",
        "condominio",
        "da",
        "das",
        "de",
        "dela",
        "dele",
        "dentro",
        "dia",
        "dias",
        "do",
        "dos",
        "duvida",
        "e",
        "em",
        "entre",
        "era",
        "essa",
        "esse",
        "esta",
        "este",
        "eu",
        "foi",
        "for",
        "funciona",
        "funcionamento",
        "ha",
        "hora",
        "horario",
        "horarios",
        "horas",
        "isso",
        "ja",
        "la",
        "mais",
        "mas",
        "me",
        "mesmo",
        "meu",
        "minha",
        "morador",
        "moradores",
        "na",
        "nao",
        "nas",
        "nem",
        "no",
        "norma",
        "normas",
        "nos",
        "num",
        "numa",
        "o",
        "onde",
        "os",
        "ou",
        "para",
        "pela",
        "pelas",
        "pelo",
        "pelos",
        "permitido",
        "pode",
        "podem",
        "por",
        "posso",
        "proibido",
        "quais",
        "qual",
        "quando",
        "que",
        "quem",
        "quero",
        "regra",
        "regras",
        "regulamento",
        "residencial",
        "aurora",
        "saber",
        "sao",
        "se",
        "sem",
        "ser",
        "seu",
        "seus",
        "so",
        "sobre",
        "sua",
        "suas",
        "tambem",
        "tem",
        "ter",
        "um",
        "uma",
        "umas",
        "uns",
        "uso",
        "usar",
    }
)


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def _stem_pt(token: str) -> str:
    if len(token) > 5 and token.endswith("oes"):
        return token[:-3] + "ao"
    if len(token) > 5 and token.endswith("ais"):
        return token[:-3] + "al"
    if len(token) > 4 and token.endswith("es"):
        return token[:-2]
    if len(token) > 4 and token.endswith("s"):
        return token[:-1]
    return token


def _tokenize(text: str) -> list[str]:
    clean = _strip_accents(text.lower())
    raw_tokens = re.findall(r"[a-z0-9]{2,}", clean)
    result: list[str] = []
    for tok in raw_tokens:
        if tok in _PT_STOPWORDS:
            continue
        stemmed = _stem_pt(tok)
        if stemmed not in _PT_STOPWORDS and len(stemmed) >= 2:
            result.append(stemmed)
    return result


def _slugify(title: str) -> str:
    clean = _strip_accents(title.lower())
    return re.sub(r"[^a-z0-9]+", "-", clean).strip("-")


@dataclass(frozen=True, slots=True)
class SecaoRegulamento:
    """Representa um capítulo individual do regulamento interno."""

    id: str
    titulo: str
    conteudo: str
    titulo_tokens: frozenset[str]
    corpo_freq: dict[str, int]


class RegulamentoIndex:
    """Índice em memória dos capítulos de dados/regulamento.md."""

    def __init__(self, secoes: list[SecaoRegulamento]) -> None:
        self._secoes = secoes
        self._by_id = {s.id: s for s in secoes}
        self._doc_freq: dict[str, int] = {}
        for secao in secoes:
            all_terms = set(secao.corpo_freq.keys()) | set(secao.titulo_tokens)
            for term in all_terms:
                self._doc_freq[term] = self._doc_freq.get(term, 0) + 1

    @classmethod
    def from_markdown_file(cls, path: Path) -> "RegulamentoIndex":
        raw_text = path.read_text(encoding="utf-8")
        lines = raw_text.splitlines()

        chunks: list[tuple[str, list[str]]] = []
        current_title: str | None = None
        current_lines: list[str] = []

        for line in lines:
            heading_match = re.match(r"^##\s+(.+?)\s*$", line)
            if heading_match:
                if current_title is not None:
                    chunks.append((current_title, current_lines))
                current_title = heading_match.group(1)
                current_lines = [line]
            elif current_title is not None:
                current_lines.append(line)

        if current_title is not None:
            chunks.append((current_title, current_lines))

        secoes: list[SecaoRegulamento] = []
        for title, body_lines in chunks:
            body_text = "\n".join(body_lines).strip()
            # Ignora o prefixo genérico "Capítulo X:" nos tokens de título
            title_subject = re.sub(
                r"^cap[ií]tulo\s+[ivxlcdm]+\s*:\s*",
                "",
                title,
                flags=re.IGNORECASE,
            )
            titulo_tokens = frozenset(_tokenize(title_subject))
            freq: dict[str, int] = {}
            for tok in _tokenize(body_text):
                freq[tok] = freq.get(tok, 0) + 1

            secoes.append(
                SecaoRegulamento(
                    id=_slugify(title),
                    titulo=title,
                    conteudo=body_text,
                    titulo_tokens=titulo_tokens,
                    corpo_freq=freq,
                )
            )
        return cls(secoes)

    @property
    def secoes(self) -> list[SecaoRegulamento]:
        return list(self._secoes)

    def listar_secoes(self) -> list[dict[str, str]]:
        return [{"secao_id": s.id, "titulo": s.titulo} for s in self._secoes]

    def ler_secao(self, secao_id: str) -> dict[str, Any]:
        alvo_norm = _slugify(secao_id)
        if alvo_norm in self._by_id:
            secao = self._by_id[alvo_norm]
            return {
                "encontrado": True,
                "secao_id": secao.id,
                "titulo": secao.titulo,
                "conteudo": secao.conteudo,
            }

        for secao in self._secoes:
            if alvo_norm and alvo_norm in secao.id:
                return {
                    "encontrado": True,
                    "secao_id": secao.id,
                    "titulo": secao.titulo,
                    "conteudo": secao.conteudo,
                }

        return {
            "encontrado": False,
            "secoes_disponiveis": self.listar_secoes(),
        }

    def buscar_capitulo(self, consulta: str) -> dict[str, Any]:
        """Retorna exclusivamente o capítulo mais pertinente (top_k=1) para a consulta."""
        query_tokens = _tokenize(consulta)
        if not query_tokens:
            return {
                "encontrado": False,
                "secoes_disponiveis": self.listar_secoes(),
            }

        n_docs = max(len(self._secoes), 1)
        best_secao: SecaoRegulamento | None = None
        best_score = 0.0

        for secao in self._secoes:
            score = 0.0
            for q_tok in set(query_tokens):
                df = self._doc_freq.get(q_tok, 0)
                idf = math.log((n_docs + 1) / (df + 1)) + 1.0
                if q_tok in secao.titulo_tokens:
                    score += 15.0 * idf
                tf = secao.corpo_freq.get(q_tok, 0)
                if tf > 0:
                    score += (1.0 + math.log(tf)) * idf

            if score > best_score:
                best_score = score
                best_secao = secao

        if best_secao is None or best_score <= 0.0:
            return {
                "encontrado": False,
                "secoes_disponiveis": self.listar_secoes(),
            }

        return {
            "encontrado": True,
            "secao_id": best_secao.id,
            "titulo": best_secao.titulo,
            "conteudo": best_secao.conteudo,
        }


@lru_cache(maxsize=1)
def get_regulamento_index() -> RegulamentoIndex:
    """Carrega e cacheia o índice por capítulos de dados/regulamento.md."""
    regulamento_path = get_settings().dados_dir / "regulamento.md"
    return RegulamentoIndex.from_markdown_file(regulamento_path)
