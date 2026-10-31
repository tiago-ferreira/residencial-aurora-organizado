"""Verifica que todos os caminhos de arquivo e trechos Python citados no README.md existem no código."""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _normalize_dedent(code: str) -> str:
    lines = [line.rstrip() for line in textwrap.dedent(code).strip().splitlines()]
    return "\n".join(lines)


def test_readme_arquivos_e_trechos_python_existem() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "## Arquitetura" in readme
    assert "## Garantias" in readme
    assert "## Como rodar" in readme
    assert "### Garantia 1:" in readme
    assert "### Garantia 2:" in readme
    assert "### Garantia 3:" in readme
    assert "### Garantia 4:" in readme
    assert "### Garantia 5:" in readme
    assert "http://localhost:8000" in readme
    assert "uv run uvicorn aurora.main:app --host 0.0.0.0 --port 8000" in readme

    file_refs = sorted(set(re.findall(r"`(src/[a-zA-Z0-9_./]+\.py)`", readme)))
    assert len(file_refs) >= 5

    all_sources_dedented: list[str] = []
    for rel_path in file_refs:
        full_path = PROJECT_ROOT / rel_path
        assert full_path.is_file(), f"Arquivo citado no README não existe: {rel_path}"
        content = full_path.read_text(encoding="utf-8")
        all_sources_dedented.append(content)

    py_blocks = re.findall(r"```python\n(.*?)```", readme, flags=re.DOTALL)
    assert len(py_blocks) >= 8

    for block in py_blocks:
        target = _normalize_dedent(block)
        matched = False
        for src in all_sources_dedented:
            src_lines = [line.rstrip() for line in src.splitlines()]
            block_lines = target.splitlines()
            n = len(block_lines)
            for idx in range(len(src_lines) - n + 1):
                window = "\n".join(src_lines[idx : idx + n])
                if _normalize_dedent(window) == target:
                    matched = True
                    break
            if matched:
                break
        assert matched, f"Trecho Python do README não encontrado literalmente nos arquivos citados:\n{target}"
