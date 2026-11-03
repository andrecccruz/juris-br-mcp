"""Fixtures globais dos testes."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _isolar_disco_e_rede(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    # Snapshots agora persistem em disco por padrão: nos testes, vão para tmp.
    monkeypatch.setenv("JURIDICO_SNAPSHOT_DIR", str(tmp_path / "snapshots"))

    # buscar_processo_por_numero complementa partes via DJEN (rede real).
    # Nos testes, devolve um stub fixo para não depender da internet.
    async def _stub(_numero: str) -> dict[str, Any]:
        return {"total_publicacoes": 0, "ultima_publicacao": None, "partes": [], "advogados": []}

    monkeypatch.setattr("juris_br_mcp.processo.tools._partes_djen", _stub)
