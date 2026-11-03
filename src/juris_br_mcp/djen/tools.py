"""Tools MCP do DJEN (Diário de Justiça Eletrônico Nacional).

Somente leitura. Consultar publicações no DJEN NÃO produz efeito jurídico
(diferente de confirmar_leitura_intimacao, do Domicílio Judicial Eletrônico).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from juris_br_mcp._core import JuridicoValidationError, get_logger
from juris_br_mcp.shared.validators import (
    diagnosticar_numero_cnj,
    normalizar_numero_cnj,
)

from .client import ITENS_POR_PAGINA_MAX, DJENClient, normalizar_comunicacao

logger = get_logger(__name__)
_client = DJENClient()

_FONTE = "DJEN - Diário de Justiça Eletrônico Nacional (API pública Comunica PJe/CNJ)"
_AVISO = (
    "Informação para uso do advogado responsável; não constitui consultoria jurídica. "
    "A contagem de prazo segue a data de publicação oficial (dia útil seguinte à "
    "disponibilização no DJEN, art. 224 CPC). Confira sempre no portal oficial."
)


def _data_iso(campo: str, valor: str | None) -> str | None:
    """Aceita YYYY-MM-DD ou DD/MM/YYYY e devolve YYYY-MM-DD."""
    if not valor:
        return None
    valor = valor.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(valor, fmt).date().isoformat()
        except ValueError:
            continue
    raise JuridicoValidationError(campo, valor, "Use o formato AAAA-MM-DD ou DD/MM/AAAA.")


def _numero(numero_processo: str | None) -> str | None:
    if not numero_processo:
        return None
    motivo = diagnosticar_numero_cnj(numero_processo)
    if motivo:
        raise JuridicoValidationError("numero_processo", numero_processo, motivo)
    return normalizar_numero_cnj(numero_processo)


async def buscar_comunicacoes_djen(
    numero_oab: str | None = None,
    uf_oab: str | None = None,
    nome_advogado: str | None = None,
    nome_parte: str | None = None,
    numero_processo: str | None = None,
    tribunal: str | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None,
    pagina: int = 1,
    itens_por_pagina: int = 20,
    max_chars_texto: int = 3000,
) -> dict[str, object]:
    """Busca publicações e intimações no DJEN (Diário de Justiça Eletrônico Nacional).

    Traz o TEXTO da publicação, partes, advogados (com OAB), link do documento no
    tribunal e a URL da certidão em PDF. Complementa o DataJud, que só tem metadados.

    Informe pelo menos um filtro: OAB, advogado, parte ou número do processo
    (tribunal e datas sozinhos também funcionam, mas retornam volume enorme).

    Args:
        numero_oab: Número da OAB (só dígitos). Use junto com uf_oab.
        uf_oab: UF da OAB (ex.: 'SP').
        nome_advogado: Nome do advogado.
        nome_parte: Nome de parte (pessoa ou empresa) destinatária.
        numero_processo: Número CNJ (com ou sem máscara).
        tribunal: Sigla do tribunal (ex.: 'TJSP', 'TRT2').
        data_inicio: Data de disponibilização inicial (AAAA-MM-DD ou DD/MM/AAAA).
        data_fim: Data de disponibilização final.
        pagina: Página (começa em 1).
        itens_por_pagina: Itens por página (máx. 100).
        max_chars_texto: Corta o texto de cada publicação neste tamanho (0 = sem corte).

    Returns:
        Total encontrado, página e a lista de comunicações normalizadas.
    """
    filtros: dict[str, Any] = {
        "numero_oab": re.sub(r"\D", "", numero_oab) if numero_oab else None,
        "uf_oab": uf_oab.strip().upper() if uf_oab else None,
        "nome_advogado": nome_advogado.strip() if nome_advogado else None,
        "nome_parte": nome_parte.strip() if nome_parte else None,
        "numero_processo": _numero(numero_processo),
        "tribunal": tribunal.strip().upper() if tribunal else None,
        "data_inicio": _data_iso("data_inicio", data_inicio),
        "data_fim": _data_iso("data_fim", data_fim),
    }
    principais = ("numero_oab", "nome_advogado", "nome_parte", "numero_processo", "tribunal")
    if not any(filtros[k] for k in principais):
        raise JuridicoValidationError(
            "filtros",
            "",
            "Informe ao menos um filtro: numero_oab, nome_advogado, nome_parte, "
            "numero_processo ou tribunal.",
        )

    logger.info("djen_buscar", **{k: v for k, v in filtros.items() if v and k != "nome_parte"})
    resultado = await _client.buscar(pagina=pagina, itens_por_pagina=itens_por_pagina, **filtros)
    itens = [normalizar_comunicacao(i, max_chars_texto) for i in resultado["items"]]

    return {
        "total_encontrado": resultado["count"],
        "pagina": max(1, pagina),
        "itens_por_pagina": min(max(1, itens_por_pagina), ITENS_POR_PAGINA_MAX),
        "retornados": len(itens),
        "comunicacoes": itens,
        "fonte": _FONTE,
        "aviso": _AVISO,
        "nota": (
            "O DJEN limita o total informado a 10.000. Refine por data ou tribunal "
            "se o total for alto."
        ),
    }


async def processos_por_parte_djen(
    nome_parte: str,
    tribunal: str | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None,
    max_paginas: int = 3,
) -> dict[str, object]:
    """Descobre os processos de uma pessoa ou empresa pelo NOME, via publicações do DJEN.

    Busca as publicações em que o nome figura como parte e agrupa por número de
    processo. Só encontra processos que tiveram alguma publicação no DJEN (não
    cobre processos sem publicação, sigilosos ou anteriores ao DJEN).

    Args:
        nome_parte: Nome completo da pessoa ou razão social (quanto mais exato, melhor).
        tribunal: Sigla do tribunal para restringir (opcional).
        data_inicio: Data inicial de disponibilização (opcional).
        data_fim: Data final de disponibilização (opcional).
        max_paginas: Quantas páginas de 100 publicações varrer (1 a 10, padrão 3).

    Returns:
        Lista de processos com tribunal, classe, partes, advogados e última publicação.
    """
    if not nome_parte or len(nome_parte.strip()) < 5:
        raise JuridicoValidationError(
            "nome_parte", nome_parte or "", "Informe o nome completo (mínimo 5 caracteres)."
        )
    max_paginas = min(max(1, max_paginas), 10)
    filtros = {
        "nome_parte": nome_parte.strip(),
        "tribunal": tribunal.strip().upper() if tribunal else None,
        "data_inicio": _data_iso("data_inicio", data_inicio),
        "data_fim": _data_iso("data_fim", data_fim),
    }

    processos: dict[str, dict[str, Any]] = {}
    total = 0
    paginas_lidas = 0
    for pagina in range(1, max_paginas + 1):
        resultado = await _client.buscar(
            pagina=pagina, itens_por_pagina=ITENS_POR_PAGINA_MAX, **filtros
        )
        total = resultado["count"]
        paginas_lidas = pagina
        for bruto in resultado["items"]:
            c = normalizar_comunicacao(bruto, max_chars_texto=0)
            numero = c["numero_processo"]
            if not numero:
                continue
            p = processos.setdefault(
                numero,
                {
                    "numero_processo": numero,
                    "tribunal": c["tribunal"],
                    "classe": c["classe"],
                    "orgao": c["orgao"],
                    "partes": {},
                    "advogados": {},
                    "total_publicacoes": 0,
                    "ultima_publicacao": None,
                    "primeira_publicacao": None,
                },
            )
            p["total_publicacoes"] += 1
            data_pub = c["data_disponibilizacao"]
            if data_pub and (not p["ultima_publicacao"] or data_pub > p["ultima_publicacao"]):
                p["ultima_publicacao"] = data_pub
                p["orgao"] = c["orgao"] or p["orgao"]
            if data_pub and (not p["primeira_publicacao"] or data_pub < p["primeira_publicacao"]):
                p["primeira_publicacao"] = data_pub
            for parte in c["partes"]:
                if parte["nome"]:
                    p["partes"][parte["nome"]] = parte["polo"]
            for adv in c["advogados"]:
                if adv["nome"]:
                    p["advogados"][f"{adv['nome']}|{adv['oab']}|{adv['uf']}"] = adv
        if len(resultado["items"]) < ITENS_POR_PAGINA_MAX:
            break

    lista = []
    for p in processos.values():
        p["partes"] = [{"nome": n, "polo": polo} for n, polo in p["partes"].items()]
        p["advogados"] = list(p["advogados"].values())
        lista.append(p)
    lista.sort(key=lambda p: p["ultima_publicacao"] or "", reverse=True)

    varredura_completa = paginas_lidas * ITENS_POR_PAGINA_MAX >= total
    return {
        "nome_pesquisado": nome_parte.strip(),
        "total_publicacoes_encontradas": total,
        "paginas_lidas": paginas_lidas,
        "varredura_completa": varredura_completa,
        "total_processos": len(lista),
        "processos": lista,
        "fonte": _FONTE,
        "aviso": (
            "A busca é por NOME: homônimos podem aparecer. Confirme pelas partes e "
            "advogados antes de concluir que o processo é da pessoa/empresa."
            + (
                ""
                if varredura_completa
                else " Nem todas as publicações foram lidas: aumente max_paginas ou "
                "restrinja por tribunal/data."
            )
        ),
    }


async def partes_do_processo_djen(numero_processo: str, limite: int = 100) -> dict[str, Any]:
    """Uso interno: partes e advogados de um processo a partir das publicações do DJEN."""
    resultado = await _client.buscar(
        pagina=1, itens_por_pagina=limite, numero_processo=normalizar_numero_cnj(numero_processo)
    )
    partes: dict[str, str | None] = {}
    advogados: dict[str, dict[str, Any]] = {}
    ultima: str | None = None
    for bruto in resultado["items"]:
        c = normalizar_comunicacao(bruto, max_chars_texto=0)
        for parte in c["partes"]:
            if parte["nome"]:
                partes[parte["nome"]] = parte["polo"]
        for adv in c["advogados"]:
            if adv["nome"]:
                advogados[f"{adv['nome']}|{adv['oab']}|{adv['uf']}"] = adv
        d = c["data_disponibilizacao"]
        if d and (ultima is None or d > ultima):
            ultima = d
    return {
        "total_publicacoes": resultado["count"],
        "ultima_publicacao": ultima,
        "partes": [{"nome": n, "polo": p} for n, p in partes.items()],
        "advogados": list(advogados.values()),
    }


__all__ = ["buscar_comunicacoes_djen", "partes_do_processo_djen", "processos_por_parte_djen"]
