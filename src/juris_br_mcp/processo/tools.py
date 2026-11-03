"""Tool MCP: buscar_processo_por_numero.

DISCLAIMER OBRIGATÓRIO (OAB Rec. 001/2024 + Provimento 205/2021):
Esta ferramenta é destinada exclusivamente ao uso por advogados e profissionais
do direito para acompanhamento de processos de seus clientes. Não constitui
consultoria jurídica. A análise final e a orientação ao cliente são de
responsabilidade exclusiva do advogado habilitado.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from juris_br_mcp._core import (
    JuridicoValidationError,
    get_logger,
)
from juris_br_mcp.datajud.provider import DataJudProvider
from juris_br_mcp.djen.tools import partes_do_processo_djen
from juris_br_mcp.shared.schemas import Processo
from juris_br_mcp.shared.validators import diagnosticar_numero_cnj, normalizar_numero_cnj

logger = get_logger(__name__)

_provider = DataJudProvider()

_DISCLAIMER = (
    "AVISO: Esta informação é fornecida para uso exclusivo do advogado responsável. "
    "Não constitui consultoria jurídica. Verifique sempre os dados diretamente no "
    "portal do tribunal antes de tomar qualquer decisão processual."
)


_LIMITE_DEFASAGEM_DIAS = 7


async def _partes_djen(numero_normalizado: str) -> dict[str, Any] | None:
    """Partes/advogados via DJEN. Falha silenciosa: é um complemento, não a fonte principal."""
    try:
        return await partes_do_processo_djen(numero_normalizado)
    except Exception as exc:
        logger.warning("djen_enriquecimento_falhou", numero=numero_normalizado, erro=str(exc))
        return None


def _info_atualizacao(processo: Processo) -> dict[str, object]:
    ultima = processo.data_ultima_atualizacao
    if ultima is None:
        return {"dias_desde_ultima_atualizacao": None, "alerta": None}
    if ultima.tzinfo is None:
        ultima = ultima.replace(tzinfo=timezone.utc)
    dias = (datetime.now(tz=timezone.utc) - ultima).days
    alerta = None
    if dias > _LIMITE_DEFASAGEM_DIAS:
        alerta = (
            f"O DataJud não recebe atualização deste processo há {dias} dias. "
            "Pode haver andamentos recentes ainda não enviados pelo tribunal: "
            "confira no portal do tribunal ou nas publicações do DJEN."
        )
    return {"dias_desde_ultima_atualizacao": dias, "alerta": alerta}


async def buscar_processo_por_numero(
    numero_processo: str,
    tribunal: str | None = None,
    incluir_partes_djen: bool = True,
) -> dict[str, object]:
    """Busca os dados de um processo judicial pelo número CNJ.

    Consulta a API pública DataJud (CNJ) e retorna metadados do processo,
    classe, assuntos, órgão julgador, todas as instâncias (1º grau, 2º grau...)
    e o histórico de movimentações de todas elas (cada uma marcada com o grau).

    A API pública do DataJud NÃO informa as partes. Com incluir_partes_djen=True,
    partes e advogados são obtidos das publicações do DJEN (quando houver).

    Cobertura: 92 siglas de tribunais cadastradas (STF, STJ, TST, TSE, STM, TRF1-6, TRTs, TJs
    estaduais, TREs e militares estaduais).

    Args:
        numero_processo: Número no formato CNJ (ex: '0001234-56.2023.8.26.0100')
                         ou sem formatação (20 dígitos).
        tribunal: Sigla do tribunal (ex: 'TJSP', 'TRF4', 'STJ'). Se omitida,
                  o tribunal é deduzido do próprio número CNJ.
        incluir_partes_djen: Completa partes e advogados com dados do DJEN (padrão True).

    Returns:
        Dicionário com dados do processo e aviso de responsabilidade.

    Raises:
        JuridicoValidationError: Número CNJ inválido (formato ou dígito verificador).
        JuridicoSigiloError: Processo em segredo de justiça.
        JuridicoNotFoundError: Processo não localizado.
    """
    motivo = diagnosticar_numero_cnj(numero_processo)
    if motivo:
        raise JuridicoValidationError(
            field="numero_processo",
            value=numero_processo,
            reason=motivo,
        )

    numero_normalizado = normalizar_numero_cnj(numero_processo)
    logger.info("buscar_processo_solicitado", numero=numero_normalizado, tribunal=tribunal)

    processo: Processo = await _provider.buscar_processo(numero_normalizado, tribunal)

    resultado: dict[str, object] = {}
    if processo.aviso_fonte:
        resultado["alerta_resultado_incompleto"] = processo.aviso_fonte
    resultado |= {
        "processo": processo.model_dump(mode="json"),
        "atualizacao": _info_atualizacao(processo),
        "aviso": _DISCLAIMER,
        "fonte": "DataJud CNJ (API Publica - Portaria CNJ 160/2020)",
        "nota_defasagem": (
            "Os dados refletem o estado registrado no DataJud, que pode ter "
            "atraso de horas a dias em relação ao portal do tribunal de origem."
        ),
    }

    if incluir_partes_djen:
        djen = await _partes_djen(numero_normalizado)
        if djen is not None:
            resultado["partes_djen"] = {
                **djen,
                "fonte": "DJEN (publicações do processo)",
                "nota": (
                    "Partes e advogados citados nas publicações do DJEN. Lista vazia "
                    "significa que o processo não teve publicação no DJEN."
                ),
            }
        else:
            resultado["partes_djen"] = {"erro": "DJEN indisponível no momento."}

    return resultado


__all__ = ["buscar_processo_por_numero"]
