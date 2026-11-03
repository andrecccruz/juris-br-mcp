"""Cliente do DJEN - Diário de Justiça Eletrônico Nacional (API pública Comunica PJe).

Endpoint público, sem autenticação:
    GET https://comunicaapi.pje.jus.br/api/v1/comunicacao
    GET https://comunicaapi.pje.jus.br/api/v1/comunicacao/{hash}/certidao  (PDF)

Diferente do DataJud, o DJEN traz o TEXTO das publicações/intimações, as partes
(destinatários) e os advogados com OAB. Não confundir com o módulo `dje`, que é
o Domicílio Judicial Eletrônico (API autenticada, com efeito jurídico).
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

import httpx

from juris_br_mcp._core import HTTPClient, JuridicoAPIError, get_logger
from juris_br_mcp._core import settings as _settings

logger = get_logger(__name__)

DJEN_BASE_URL = "https://comunicaapi.pje.jus.br/api/v1"
ITENS_POR_PAGINA_MAX = 100

# Nome do parametro da tool -> nome do parametro na API
_PARAMS_API = {
    "numero_oab": "numeroOab",
    "uf_oab": "ufOab",
    "nome_advogado": "nomeAdvogado",
    "nome_parte": "nomeParte",
    "numero_processo": "numeroProcesso",
    "tribunal": "siglaTribunal",
    "data_inicio": "dataDisponibilizacaoInicio",
    "data_fim": "dataDisponibilizacaoFim",
    "meio": "meio",
}

_POLOS = {"A": "ativo", "P": "passivo", "T": "terceiro"}


class _HTMLParaTexto(HTMLParser):
    _BLOCOS = frozenset(
        {
            "p",
            "div",
            "br",
            "section",
            "article",
            "header",
            "footer",
            "li",
            "tr",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "table",
            "ul",
            "ol",
        }
    )
    _IGNORAR = frozenset({"style", "script", "head"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.partes: list[str] = []
        self._ignorando = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._IGNORAR:
            self._ignorando += 1
        elif tag in self._BLOCOS:
            self.partes.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._IGNORAR:
            self._ignorando = max(0, self._ignorando - 1)
        elif tag in self._BLOCOS:
            self.partes.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignorando:
            self.partes.append(data)


def html_para_texto(html: str | None) -> str:
    """Converte o HTML das publicações do DJEN em texto limpo."""
    if not html:
        return ""
    if "<" not in html:
        return html.strip()
    parser = _HTMLParaTexto()
    parser.feed(html)
    texto = "".join(parser.partes).replace("\xa0", " ")
    texto = re.sub(r"[ \t\r\f\v]+", " ", texto)
    texto = re.sub(r" *\n *", "\n", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def url_certidao(hash_comunicacao: str) -> str:
    return f"{DJEN_BASE_URL}/comunicacao/{hash_comunicacao}/certidao"


def normalizar_comunicacao(item: dict[str, Any], max_chars_texto: int | None) -> dict[str, Any]:
    """Reduz um item bruto do DJEN aos campos úteis, com texto já limpo."""
    texto = html_para_texto(item.get("texto"))
    truncado = max_chars_texto is not None and max_chars_texto > 0 and len(texto) > max_chars_texto
    if truncado:
        texto = texto[:max_chars_texto].rstrip() + " [...]"
    hash_ = item.get("hash")
    return {
        "id": item.get("id"),
        "data_disponibilizacao": item.get("data_disponibilizacao"),
        "tribunal": item.get("siglaTribunal"),
        "numero_processo": item.get("numeroprocessocommascara") or item.get("numero_processo"),
        "classe": item.get("nomeClasse"),
        "tipo_comunicacao": item.get("tipoComunicacao"),
        "tipo_documento": item.get("tipoDocumento"),
        "orgao": item.get("nomeOrgao"),
        "meio": item.get("meiocompleto") or item.get("meio"),
        "texto": texto,
        "texto_truncado": truncado,
        "link_documento": item.get("link"),
        "hash": hash_,
        "url_certidao": url_certidao(hash_) if hash_ else None,
        "ativo": item.get("ativo"),
        "cancelamento": (
            {"data": item.get("data_cancelamento"), "motivo": item.get("motivo_cancelamento")}
            if item.get("data_cancelamento")
            else None
        ),
        "partes": [
            {"nome": d.get("nome"), "polo": _POLOS.get(d.get("polo") or "", d.get("polo"))}
            for d in item.get("destinatarios") or []
        ],
        "advogados": [
            {
                "nome": (a.get("advogado") or {}).get("nome"),
                "oab": (a.get("advogado") or {}).get("numero_oab"),
                "uf": (a.get("advogado") or {}).get("uf_oab"),
            }
            for a in item.get("destinatarioadvogados") or []
        ],
    }


class DJENClient:
    """Acesso à API pública do DJEN (Comunica PJe)."""

    def __init__(self) -> None:
        self._http = HTTPClient(
            base_url=DJEN_BASE_URL,
            headers={"User-Agent": "juris-br-mcp", "Accept": "application/json"},
            timeout=_settings.juridico_http_timeout,
            max_retries=_settings.juridico_max_retries,
            cache_ttl=_settings.juridico_cache_ttl,
            rate_limit_per_second=_settings.juridico_rate_limit,
        )

    async def buscar(
        self, pagina: int = 1, itens_por_pagina: int = 20, **filtros: Any
    ) -> dict[str, Any]:
        """Consulta /comunicacao. Filtros usam os nomes de `_PARAMS_API`.

        Returns:
            {"count": int, "items": [itens brutos da API]}
        """
        params: dict[str, Any] = {
            "pagina": max(1, pagina),
            "itensPorPagina": min(max(1, itens_por_pagina), ITENS_POR_PAGINA_MAX),
        }
        for nome, valor in filtros.items():
            if valor in (None, ""):
                continue
            if nome not in _PARAMS_API:
                raise ValueError(f"Filtro DJEN desconhecido: {nome}")
            params[_PARAMS_API[nome]] = valor

        try:
            data = await self._http.get("/comunicacao", params=params)
        except httpx.HTTPStatusError as exc:
            corpo = exc.response.text[:300]
            raise JuridicoAPIError(
                source="DJEN",
                status_code=exc.response.status_code,
                reason=f"Consulta ao DJEN falhou: {corpo}",
            ) from exc
        if not isinstance(data, dict):
            raise JuridicoAPIError(source="DJEN", reason="Resposta inesperada do DJEN.")
        return {"count": int(data.get("count") or 0), "items": data.get("items") or []}


__all__ = [
    "DJEN_BASE_URL",
    "ITENS_POR_PAGINA_MAX",
    "DJENClient",
    "html_para_texto",
    "normalizar_comunicacao",
    "url_certidao",
]
