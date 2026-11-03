"""Consulta direta às tools do Juris BR MCP, sem cliente MCP nem modelo de linguagem.

As tools são funções Python async comuns: dá para chamá-las de scripts, planilhas,
agendadores etc. sem gastar tokens. A saída é o mesmo JSON que o cliente MCP recebe.

Uso (na raiz do repositório):
  uv run python examples/consulta_direta.py processo 0701300-13.2011.8.26.0020 [TJSP]
  uv run python examples/consulta_direta.py movimentacoes 0701300-13.2011.8.26.0020 TJSP [limite]
  uv run python examples/consulta_direta.py oab 123456 SP [data_inicio] [data_fim]
  uv run python examples/consulta_direta.py publicacoes 0701300-13.2011.8.26.0020
  uv run python examples/consulta_direta.py parte "NOME COMPLETO DA PARTE" [tribunal]
  uv run python examples/consulta_direta.py tribunais

Datas: AAAA-MM-DD ou DD/MM/AAAA.
"""

from __future__ import annotations

import asyncio
import json
import sys

from juris_br_mcp._core import configure_logging
from juris_br_mcp.djen.tools import buscar_comunicacoes_djen, processos_por_parte_djen
from juris_br_mcp.movimentacoes.tools import listar_movimentacoes
from juris_br_mcp.processo.tools import buscar_processo_por_numero
from juris_br_mcp.server import listar_tribunais


def _arg(lista: list[str], i: int) -> str | None:
    return lista[i] if len(lista) > i else None


async def main(args: list[str]) -> int:
    if not args:
        print(__doc__)
        return 1
    cmd, rest = args[0], args[1:]
    if cmd == "processo" and rest:
        resultado = await buscar_processo_por_numero(rest[0], _arg(rest, 1))
    elif cmd == "movimentacoes" and len(rest) >= 2:
        limite = int(rest[2]) if len(rest) > 2 else 20
        resultado = await listar_movimentacoes(rest[0], rest[1], limite)
    elif cmd == "oab" and len(rest) >= 2:
        resultado = await buscar_comunicacoes_djen(
            numero_oab=rest[0],
            uf_oab=rest[1],
            data_inicio=_arg(rest, 2),
            data_fim=_arg(rest, 3),
            itens_por_pagina=50,
        )
    elif cmd == "publicacoes" and rest:
        resultado = await buscar_comunicacoes_djen(
            numero_processo=rest[0], itens_por_pagina=50, max_chars_texto=0
        )
    elif cmd == "parte" and rest:
        resultado = await processos_por_parte_djen(rest[0], tribunal=_arg(rest, 1))
    elif cmd == "tribunais":
        resultado = await listar_tribunais()
    else:
        print(__doc__)
        return 1
    print(json.dumps(resultado, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    configure_logging("ERROR")  # logs vão para stderr; stdout fica só com o JSON
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(asyncio.run(main(sys.argv[1:])))
