"""Testes das melhorias: digito verificador CNJ, multi-instancia DataJud, DJEN, persistencia."""

from __future__ import annotations

from typing import Any

import pytest
import respx
from httpx import Response

from juris_br_mcp._core.errors import JuridicoSigiloError, JuridicoValidationError
from juris_br_mcp.datajud.client import DataJudClient
from juris_br_mcp.djen.client import html_para_texto, normalizar_comunicacao
from juris_br_mcp.shared.validators import (
    calcular_digito_cnj,
    diagnosticar_numero_cnj,
    validar_numero_cnj,
)

NUMERO = "07013001320118260020"  # numero real do TJSP (G1 + G2 no DataJud)
TJSP_SEARCH = "https://api-publica.datajud.cnj.jus.br/api_publica_tjsp/_search/"
DJEN_URL = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"

# ---------------------------------------------------------------------------
# Digito verificador
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("numero", "dv"),
    [("0005046-79.2024.8.26.0405", 79), ("0701300-13.2011.8.26.0020", 13)],
)
def test_digito_cnj_numeros_reais(numero: str, dv: int) -> None:
    assert calcular_digito_cnj(numero) == dv
    assert validar_numero_cnj(numero)


def test_digito_errado_e_rejeitado_com_motivo() -> None:
    numero = "0005046-80.2024.8.26.0405"
    assert not validar_numero_cnj(numero)
    motivo = diagnosticar_numero_cnj(numero)
    assert motivo is not None
    assert "esperado 79" in motivo


def test_formato_invalido_tem_motivo_de_formato() -> None:
    motivo = diagnosticar_numero_cnj("123")
    assert motivo is not None
    assert "Formato" in motivo


# ---------------------------------------------------------------------------
# DataJud: varias instancias
# ---------------------------------------------------------------------------


def _doc(
    grau: str, atualizacao: str, movs: list[tuple[str, str]], sigilo: int = 0
) -> dict[str, Any]:
    return {
        "_source": {
            "numeroProcesso": NUMERO,
            "tribunal": "TJSP",
            "grau": grau,
            "nivelSigilo": sigilo,
            "dataAjuizamento": "2011-05-10T00:00:00Z" if grau == "G1" else "2025-01-10T00:00:00Z",
            "dataHoraUltimaAtualizacao": atualizacao,
            "classe": {"codigo": 1, "nome": f"Classe {grau}"},
            "orgaoJulgador": {"codigo": 1, "nome": f"Orgao {grau}"},
            "assuntos": [{"codigo": 10, "nome": "Assunto"}],
            "movimentos": [{"codigo": 1, "nome": n, "dataHora": d} for n, d in movs],
        }
    }


@pytest.mark.asyncio
async def test_consolida_g1_e_g2() -> None:
    payload = {
        "hits": {
            "hits": [
                _doc("G1", "2026-10-02T20:00:00Z", [("Sentenca", "2024-01-01T00:00:00Z")]),
                _doc("G2", "2026-10-24T04:00:00Z", [("Acordao", "2026-10-20T00:00:00Z")]),
            ]
        }
    }
    with respx.mock:
        rota = respx.post(TJSP_SEARCH).mock(return_value=Response(200, json=payload))
        p = await DataJudClient().buscar_por_numero(NUMERO, "TJSP")

    import json

    assert json.loads(rota.calls[0].request.content)["size"] > 1
    assert p.grau == "G2"  # instancia atualizada mais recentemente
    assert p.classe_nome == "Classe G2"
    assert [i.grau for i in p.instancias] == ["G2", "G1"]
    assert [(m.nome, m.grau) for m in p.movimentacoes] == [("Acordao", "G2"), ("Sentenca", "G1")]
    assert p.data_ajuizamento is not None and p.data_ajuizamento.year == 2011


@pytest.mark.asyncio
async def test_sigilo_em_qualquer_instancia_bloqueia() -> None:
    payload = {
        "hits": {
            "hits": [
                _doc("G1", "2026-10-02T20:00:00Z", []),
                _doc("G2", "2026-10-24T04:00:00Z", [], sigilo=1),
            ]
        }
    }
    with respx.mock:
        respx.post(TJSP_SEARCH).mock(return_value=Response(200, json=payload))
        with pytest.raises(JuridicoSigiloError):
            await DataJudClient().buscar_por_numero(NUMERO, "TJSP")


@pytest.mark.asyncio
async def test_cliente_reaproveitado_e_cache() -> None:
    payload = {"hits": {"hits": [_doc("G1", "2026-10-02T20:00:00Z", [])]}}
    client = DataJudClient()
    with respx.mock:
        rota = respx.post(TJSP_SEARCH).mock(return_value=Response(200, json=payload))
        await client.buscar_por_numero(NUMERO, "TJSP")
        await client.buscar_por_numero(NUMERO, "TJSP")
    assert rota.call_count == 1  # segunda vez veio do cache
    assert client._http("tjsp") is client._http("TJSP")


@pytest.mark.asyncio
async def test_resultado_parcial_vazio_nao_vira_nao_encontrado() -> None:
    from juris_br_mcp._core.errors import JuridicoAPIError

    payload = {"_shards": {"total": 20, "successful": 12, "failed": 8}, "hits": {"hits": []}}
    client = DataJudClient()
    with respx.mock:
        rota = respx.post(TJSP_SEARCH).mock(return_value=Response(200, json=payload))
        with pytest.raises(JuridicoAPIError, match="parcial"):
            await client.buscar_por_numero(NUMERO, "TJSP")
        with pytest.raises(JuridicoAPIError):
            await client.buscar_por_numero(NUMERO, "TJSP")
    assert rota.call_count == 2  # resposta parcial nao foi para o cache


@pytest.mark.asyncio
async def test_resultado_parcial_com_dados_traz_aviso() -> None:
    payload = {
        "_shards": {"total": 20, "successful": 12, "failed": 8},
        "hits": {"hits": [_doc("G1", "2026-10-02T20:00:00Z", [])]},
    }
    with respx.mock:
        respx.post(TJSP_SEARCH).mock(return_value=Response(200, json=payload))
        p = await DataJudClient().buscar_por_numero(NUMERO, "TJSP")
    assert p.aviso_fonte is not None and "parcial" in p.aviso_fonte


@pytest.mark.asyncio
async def test_tribunal_deduzido_sobrecarregado_nao_varre_os_demais() -> None:
    from juris_br_mcp._core.errors import JuridicoAPIError

    with respx.mock:
        respx.post(TJSP_SEARCH).mock(return_value=Response(429, json={"error": "rejected"}))
        outros = respx.post(url__regex=r".*api_publica_(?!tjsp).*").mock(
            return_value=Response(200, json={"hits": {"hits": []}})
        )
        with pytest.raises(JuridicoAPIError, match="sobrecarregado"):
            await DataJudClient().buscar_por_numero_multiplos_tribunais(NUMERO)
    assert outros.call_count == 0


# ---------------------------------------------------------------------------
# DJEN
# ---------------------------------------------------------------------------

_ITEM_DJEN = {
    "id": 1,
    "data_disponibilizacao": "2026-10-28",
    "siglaTribunal": "TJSP",
    "tipoComunicacao": "Intimação",
    "nomeOrgao": "1ª Vara Cível",
    "texto": "<html><head><style>x{}</style></head><body><p>Fica a parte&nbsp;<b>intimada</b>.</p>"
    "<p>Prazo: 15 dias.</p></body></html>",
    "numero_processo": "00050467920248260405",
    "numeroprocessocommascara": "0005046-79.2024.8.26.0405",
    "link": "https://exemplo/doc",
    "nomeClasse": "PROCEDIMENTO COMUM",
    "hash": "abc123",
    "ativo": True,
    "destinatarios": [{"nome": "FULANO", "polo": "A"}, {"nome": "EMPRESA X", "polo": "P"}],
    "destinatarioadvogados": [
        {"advogado": {"nome": "ADV UM", "numero_oab": "123", "uf_oab": "SP"}}
    ],
}


def test_html_para_texto() -> None:
    texto = html_para_texto(_ITEM_DJEN["texto"])
    assert texto == "Fica a parte intimada.\n\nPrazo: 15 dias."


def test_normalizar_comunicacao() -> None:
    c = normalizar_comunicacao(_ITEM_DJEN, max_chars_texto=10)
    assert c["numero_processo"] == "0005046-79.2024.8.26.0405"
    assert c["texto_truncado"] is True
    assert c["url_certidao"].endswith("/comunicacao/abc123/certidao")
    assert c["partes"] == [
        {"nome": "FULANO", "polo": "ativo"},
        {"nome": "EMPRESA X", "polo": "passivo"},
    ]
    assert c["advogados"] == [{"nome": "ADV UM", "oab": "123", "uf": "SP"}]


@pytest.mark.asyncio
async def test_buscar_comunicacoes_exige_filtro() -> None:
    from juris_br_mcp.djen.tools import buscar_comunicacoes_djen

    with pytest.raises(JuridicoValidationError):
        await buscar_comunicacoes_djen(data_inicio="2026-10-01")


@pytest.mark.asyncio
async def test_buscar_comunicacoes_por_oab_monta_parametros() -> None:
    from juris_br_mcp.djen import tools

    tools._client = tools.DJENClient()  # cache limpo
    with respx.mock:
        rota = respx.get(DJEN_URL).mock(
            return_value=Response(
                200, json={"status": "success", "count": 1, "items": [_ITEM_DJEN]}
            )
        )
        r = await tools.buscar_comunicacoes_djen(
            numero_oab="123.456", uf_oab="sp", data_inicio="01/10/2026"
        )
    params = dict(rota.calls[0].request.url.params)
    assert params["numeroOab"] == "123456"
    assert params["ufOab"] == "SP"
    assert params["dataDisponibilizacaoInicio"] == "2026-10-01"
    assert r["total_encontrado"] == 1
    assert r["comunicacoes"][0]["texto"].startswith("Fica a parte intimada")


@pytest.mark.asyncio
async def test_processos_por_parte_agrupa() -> None:
    from juris_br_mcp.djen import tools

    tools._client = tools.DJENClient()
    item2 = {**_ITEM_DJEN, "id": 2, "data_disponibilizacao": "2026-10-30"}
    outro = {
        **_ITEM_DJEN,
        "id": 3,
        "numeroprocessocommascara": "0701300-13.2011.8.26.0020",
        "data_disponibilizacao": "2026-09-01",
    }
    with respx.mock:
        respx.get(DJEN_URL).mock(
            return_value=Response(200, json={"count": 3, "items": [_ITEM_DJEN, item2, outro]})
        )
        r = await tools.processos_por_parte_djen("EMPRESA X")
    assert r["total_processos"] == 2
    primeiro = r["processos"][0]
    assert primeiro["numero_processo"] == "0005046-79.2024.8.26.0405"
    assert primeiro["total_publicacoes"] == 2
    assert primeiro["ultima_publicacao"] == "2026-10-30"
    assert r["varredura_completa"] is True


# ---------------------------------------------------------------------------
# Persistencia de snapshots
# ---------------------------------------------------------------------------


def test_snapshot_persiste_e_lista_do_disco(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    from juris_br_mcp.monitoramento import store

    monkeypatch.setenv("JURIDICO_SNAPSHOT_DIR", str(tmp_path))
    store.salvar_snapshot("123", "TJSP", {"a": 1})
    with store._lock:
        store._snapshots.clear()  # simula reinicio do servidor
    assert "123" in store.listar_processos_monitorados()
    assert store.obter_snapshot("123")["dados"] == {"a": 1}


def test_snapshot_modo_memoria(monkeypatch: pytest.MonkeyPatch) -> None:
    from juris_br_mcp.monitoramento import store

    monkeypatch.setenv("JURIDICO_SNAPSHOT_DIR", "memoria")
    assert store._snapshot_path("123") is None


def test_snapshot_padrao_em_home(monkeypatch: pytest.MonkeyPatch) -> None:
    from juris_br_mcp.monitoramento import store

    monkeypatch.delenv("JURIDICO_SNAPSHOT_DIR", raising=False)
    assert store._snapshot_dir() == store._PADRAO_DIR
