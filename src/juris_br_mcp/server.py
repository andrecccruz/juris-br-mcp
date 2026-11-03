"""Servidor Juris BR MCP.

Registra tools e resources no FastMCP e expõe o servidor via stdio (padrão)
ou HTTP streamable (Smithery/Docker).

Tools expostas (Fase 4):
- buscar_processo_por_numero  : consulta completa por número CNJ
- listar_movimentacoes        : histórico de andamentos
- resumir_andamento           : dados + instrução de resumo para o LLM
- monitorar_processo          : verifica atualização desde data (polling)
- calcular_proximo_prazo      : cálculo em dias úteis com calendário forense
- listar_processos_monitorados: lista processos com snapshot em memória
- listar_tribunais            : lista de siglas suportadas
- listar_intimacoes           : comunicações do DJe (somente leitura)
- confirmar_leitura_intimacao : marca leitura no DJe (EFEITO JURÍDICO - gate duplo)

Resources expostos (Fase 2):
- processo://{numero_processo}/snapshot  : último snapshot do processo
"""

from __future__ import annotations

import json

import fastmcp

from juris_br_mcp._core import configure_logging, settings
from juris_br_mcp.datajud.tribunais import listar_tribunais as _listar_tribunais
from juris_br_mcp.dje.tools import confirmar_leitura_intimacao, listar_intimacoes
from juris_br_mcp.djen.tools import buscar_comunicacoes_djen, processos_por_parte_djen
from juris_br_mcp.monitoramento.store import (
    listar_processos_monitorados as _listar_monitorados,
)
from juris_br_mcp.monitoramento.store import (
    obter_snapshot,
)
from juris_br_mcp.monitoramento.tools import monitorar_processo
from juris_br_mcp.movimentacoes.tools import listar_movimentacoes
from juris_br_mcp.prazo.tools import calcular_proximo_prazo
from juris_br_mcp.processo.tools import buscar_processo_por_numero
from juris_br_mcp.resumo.tools import resumir_andamento

app = fastmcp.FastMCP(
    name="Juris BR MCP",
    version="0.2.0",
    instructions=(
        "Ferramentas de acompanhamento de processos judiciais brasileiros via DataJud CNJ. "
        "92 siglas de tribunais cadastradas. Dados com possível defasagem de T+1 a T+7 dias. "
        "Fase 2: cálculo de prazos em dias úteis (art. 219/220/224 CPC) com calendário "
        "forense nacional e estadual. "
        "Fase 4: acesso ao Domicílio Judicial Eletrônico (DJe) via API Comunica. "
        "DJEN (Diário de Justiça Eletrônico Nacional): texto das publicações/intimações "
        "por OAB, advogado, parte ou processo, e descoberta de processos pelo nome da parte "
        "(buscar_comunicacoes_djen, processos_por_parte_djen) - somente leitura, sem efeito "
        "jurídico. O DataJud não informa partes; use o DJEN para isso. "
        "AVISO CRÍTICO DJe: confirmar_leitura_intimacao tem EFEITO JURÍDICO REAL e inicia "
        "prazo processual. Opera em dry-run por padrão - requer gate duplo explícito. "
        "AVISO GERAL: Estas ferramentas são destinadas a advogados e profissionais do direito. "
        "Não constituem consultoria jurídica. A análise final é responsabilidade do "
        "advogado habilitado (OAB Recomendação 001/2024 | Resolução CNJ 455/2022)."
    ),
)

# ---------------------------------------------------------------------------
# Tools registradas
# ---------------------------------------------------------------------------

app.tool()(buscar_processo_por_numero)
app.tool()(listar_movimentacoes)
app.tool()(resumir_andamento)
app.tool()(monitorar_processo)
app.tool()(calcular_proximo_prazo)
app.tool()(listar_intimacoes)
app.tool()(confirmar_leitura_intimacao)
app.tool()(buscar_comunicacoes_djen)
app.tool()(processos_por_parte_djen)


@app.tool()
async def listar_tribunais() -> dict[str, object]:
    """Lista as siglas de tribunais cadastradas no MCP (92 ao total).

    Retorna siglas que podem ser usadas no parâmetro 'tribunal' das demais tools.
    """
    tribunais = _listar_tribunais()
    return {
        "total": len(tribunais),
        "tribunais": tribunais,
        "nota": (
            "Siglas baseadas no cadastro DataJud CNJ (Portaria 160/2020). "
            "Use exatamente estas siglas no parâmetro 'tribunal' das demais tools."
        ),
    }


@app.tool()
async def listar_processos_monitorados() -> dict[str, object]:
    """Lista processos com snapshot salvo (memória e disco).

    Retorna os números de processos que tiveram snapshot salvo.
    Use o resource processo://{numero}/snapshot para ler os dados completos.

    Returns:
        Dicionário com lista de números e total.
    """
    numeros = _listar_monitorados()
    return {
        "total": len(numeros),
        "processos": numeros,
        "nota": (
            "Snapshots persistidos em ~/.juris-br-mcp/snapshots (padrão). "
            "Use JURIDICO_SNAPSHOT_DIR para trocar a pasta ou 'memoria' para não gravar."
        ),
    }


# ---------------------------------------------------------------------------
# Resources MCP (Fase 2)
# ---------------------------------------------------------------------------


@app.resource("processo://{numero_processo}/snapshot")
async def resource_snapshot_processo(numero_processo: str) -> str:
    """Snapshot mais recente de um processo monitorado.

    Retorna os dados capturados na última chamada a monitorar_processo
    ou buscar_processo_por_numero para este número de processo.

    Args:
        numero_processo: Número CNJ do processo (normalizado, sem formatação).

    Returns:
        JSON com dados do snapshot ou mensagem de ausência.
    """
    snapshot = obter_snapshot(numero_processo)
    if snapshot is None:
        return json.dumps(
            {
                "encontrado": False,
                "numero_processo": numero_processo,
                "mensagem": (
                    "Nenhum snapshot disponível para este processo. "
                    "Chame buscar_processo_por_numero ou monitorar_processo primeiro."
                ),
            },
            ensure_ascii=False,
        )
    return json.dumps(
        {"encontrado": True, **snapshot},
        ensure_ascii=False,
        default=str,
        indent=2,
    )


def main() -> None:
    configure_logging(settings.juridico_log_level)
    app.run()


if __name__ == "__main__":
    main()
