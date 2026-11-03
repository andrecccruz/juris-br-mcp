"""Cliente DataJud CNJ.

Consome a API pública Elasticsearch do DataJud (Portaria CNJ 160/2020).
Chave de acesso pública - sem cadastro. Rotacionar se o CNJ revogar.

NOTA DE SEGURANÇA: Esta implementação verifica nivel_sigilo antes de retornar
qualquer dado. Processos sigilosos lançam JuridicoSigiloError e NÃO são
armazenados em cache nem em logs detalhados.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from juris_br_mcp._core import (
    HTTPClient,
    JuridicoAPIError,
    JuridicoNotFoundError,
    JuridicoSigiloError,
    get_logger,
)
from juris_br_mcp._core import (
    settings as _settings,
)
from juris_br_mcp.shared.schemas import (
    Assunto,
    Instancia,
    Movimentacao,
    OrgaoJulgador,
    Parte,
    Processo,
)

from .tribunais import indice_para_url, listar_tribunais, sigla_por_numero_cnj

logger = get_logger(__name__)


def _shards_falhos(data: Any) -> int:
    """Quantos shards do Elasticsearch falharam (resposta HTTP 200 mas incompleta)."""
    if not isinstance(data, dict):
        return 0
    try:
        return int(data.get("_shards", {}).get("failed", 0) or 0)
    except (TypeError, ValueError):
        return 0


# Um mesmo numero CNJ costuma ter 1 documento por grau (G1, G2, JE, TR...).
# 10 cobre com folga todas as instancias de um processo.
_MAX_INSTANCIAS = 10


class DataJudClient:
    """Acesso à API pública DataJud com verificação de sigilo integrada."""

    def __init__(self) -> None:
        # Um HTTPClient persistente por tribunal: reaproveita conexao, cache TTL
        # e rate limit entre chamadas (antes era recriado a cada consulta).
        self._clients: dict[str, HTTPClient] = {}

    def _http(self, tribunal: str) -> HTTPClient:
        chave = tribunal.upper()
        if chave in self._clients:
            return self._clients[chave]
        url = indice_para_url(tribunal, _settings.datajud_base_url)
        if not url:
            raise JuridicoAPIError(
                source="DataJud",
                reason=f"Tribunal '{tribunal}' não suportado. "
                f"Consulte listar_tribunais() para opções válidas.",
            )
        client = HTTPClient(
            base_url=url,
            headers={"Authorization": f"APIKey {_settings.datajud_api_key}"},
            timeout=max(_settings.juridico_http_timeout, _settings.datajud_timeout),
            max_retries=_settings.juridico_max_retries,
            cache_ttl=_settings.juridico_cache_ttl,
            rate_limit_per_second=_settings.juridico_rate_limit,
        )
        self._clients[chave] = client
        return client

    async def buscar_por_numero(self, numero_processo: str, tribunal: str) -> Processo:
        """Busca um processo pelo número CNJ em um tribunal específico.

        Retorna todas as instâncias (G1, G2...) consolidadas: os metadados vêm
        da instância atualizada mais recentemente e as movimentações de todas.

        Raises:
            JuridicoSigiloError: Se nivel_sigilo > 0 em qualquer instância.
            JuridicoNotFoundError: Se o processo não existir no índice.
            JuridicoAPIError: Em falhas de comunicação.
        """
        query = {
            "query": {"match": {"numeroProcesso": numero_processo}},
            "size": _MAX_INSTANCIAS,
        }
        client = self._http(tribunal)
        try:
            data = await client.post(
                "", json=query, use_cache=True, cache_valido=lambda d: not _shards_falhos(d)
            )
        except httpx.HTTPStatusError as exc:
            # O metodo documenta JuridicoAPIError para falhas de
            # comunicacao; sem esta conversao a HTTPStatusError crua
            # escapava e abortava a varredura multi-tribunal.
            motivo = f"Consulta ao indice do tribunal '{tribunal}' falhou."
            if exc.response.status_code == 429:
                motivo = (
                    f"DataJud sobrecarregado (índice {tribunal} recusou a consulta). "
                    "Tente novamente em alguns minutos."
                )
            raise JuridicoAPIError(
                source="DataJud",
                status_code=exc.response.status_code,
                reason=motivo,
            ) from exc
        except httpx.TimeoutException as exc:
            raise JuridicoAPIError(
                source="DataJud",
                reason=f"Sem resposta do índice {tribunal} (timeout). Tente novamente mais tarde.",
            ) from exc

        hits = data.get("hits", {}).get("hits", [])
        fontes = [h.get("_source", {}) for h in hits]
        # match em campo keyword pode trazer ruído; mantém só o número exato
        fontes = [s for s in fontes if s.get("numeroProcesso", numero_processo) == numero_processo]

        falhos = _shards_falhos(data)
        if falhos:
            total = data.get("_shards", {}).get("total", "?")
            logger.warning(
                "datajud_resultado_parcial", tribunal=tribunal, falhos=falhos, total=total
            )
            if not fontes:
                # Resposta parcial vazia NÃO prova que o processo não existe.
                raise JuridicoAPIError(
                    source="DataJud",
                    reason=(
                        f"Resultado parcial: {falhos} de {total} partes do índice {tribunal} "
                        "falharam (DataJud sobrecarregado). Não é possível afirmar que o "
                        "processo não existe; tente novamente em alguns minutos."
                    ),
                )

        if not fontes:
            raise JuridicoNotFoundError(numero_processo, tribunal)

        processo = self._consolidar(fontes, numero_processo)
        if falhos:
            processo.aviso_fonte = (
                f"O DataJud respondeu de forma parcial ({falhos} de "
                f"{data.get('_shards', {}).get('total', '?')} partes do índice falharam). "
                "Pode faltar alguma instância (ex.: 2º grau). Repita a consulta mais tarde."
            )
        return processo

    async def buscar_por_numero_multiplos_tribunais(
        self,
        numero_processo: str,
        tribunais: list[str] | None = None,
    ) -> Processo:
        """Tenta localizar o processo em múltiplos tribunais.

        Útil quando o tribunal não é conhecido de antemão.
        Itera pelos tribunais informados (ou por todos os suportados) até
        encontrar o processo.
        """
        provavel: str | None = None
        if tribunais:
            targets = tribunais
        else:
            targets = listar_tribunais()
            # O proprio numero CNJ identifica o tribunal (segmentos J e TR):
            # tentar por ele primeiro resolve em 1 requisicao em vez de ate 92.
            provavel = sigla_por_numero_cnj(numero_processo)
            if provavel:
                targets = [provavel] + [t for t in targets if t != provavel]

        last_error: Exception | None = None
        for i, tribunal in enumerate(targets):
            try:
                return await self.buscar_por_numero(numero_processo, tribunal)
            except JuridicoSigiloError:
                raise  # Sigilo nao deve ser ignorado
            except JuridicoAPIError as exc:
                # O tribunal deduzido do numero CNJ esta fora do ar/sobrecarregado:
                # varrer os outros 91 indices so pioraria (e o processo quase
                # certamente esta nele). Reporta a indisponibilidade.
                if i == 0 and not tribunais and provavel:
                    raise
                last_error = exc
                continue
            except JuridicoNotFoundError as exc:
                last_error = exc
                continue
        raise last_error or JuridicoNotFoundError(numero_processo)

    async def listar_movimentacoes(
        self, numero_processo: str, tribunal: str, limite: int = 20
    ) -> list[Movimentacao]:
        """Retorna as movimentacoes mais recentes de um processo."""
        processo = await self.buscar_por_numero(numero_processo, tribunal)
        return processo.movimentacoes[:limite]

    # ------------------------------------------------------------------
    # Parsing interno
    # ------------------------------------------------------------------

    def _consolidar(self, fontes: list[dict[str, Any]], numero: str) -> Processo:
        """Junta os documentos de cada instância num único Processo."""
        processos = [self._parse_processo(src, numero) for src in fontes]  # checa sigilo em todos
        if len(processos) == 1:
            p = processos[0]
            p.instancias = [self._resumo_instancia(p)]
            return p

        def chave_atualizacao(p: Processo) -> datetime:
            return p.data_ultima_atualizacao or datetime.min.replace(tzinfo=timezone.utc)

        principal = max(processos, key=chave_atualizacao)

        vistos: set[tuple[Any, ...]] = set()
        movs: list[Movimentacao] = []
        for p in processos:
            for m in p.movimentacoes:
                chave = (m.codigo, m.nome, m.data_hora, m.grau)
                if chave not in vistos:
                    vistos.add(chave)
                    movs.append(m)
        movs.sort(key=lambda m: m.data_hora, reverse=True)

        assuntos = {a.codigo: a for p in processos for a in p.assuntos}
        ajuizamentos = [p.data_ajuizamento for p in processos if p.data_ajuizamento]

        return principal.model_copy(
            update={
                "movimentacoes": movs,
                "assuntos": list(assuntos.values()),
                "data_ajuizamento": min(ajuizamentos) if ajuizamentos else None,
                "instancias": [
                    self._resumo_instancia(p)
                    for p in sorted(processos, key=chave_atualizacao, reverse=True)
                ],
            }
        )

    @staticmethod
    def _resumo_instancia(p: Processo) -> Instancia:
        return Instancia(
            grau=p.grau,
            orgao_julgador=p.orgao_julgador.nome if p.orgao_julgador else None,
            classe_nome=p.classe_nome,
            sistema=p.sistema,
            data_ultima_atualizacao=p.data_ultima_atualizacao,
            total_movimentacoes=len(p.movimentacoes),
        )

    def _parse_processo(self, src: dict[str, Any], numero_fallback: str) -> Processo:
        nivel_sigilo = int(src.get("nivelSigilo", 0))
        numero = src.get("numeroProcesso", numero_fallback)

        if nivel_sigilo > 0:
            logger.warning("processo_sigiloso_bloqueado", nivel=nivel_sigilo)
            raise JuridicoSigiloError(numero, nivel_sigilo)

        classe = src.get("classe", {})
        orgao = src.get("orgaoJulgador", {})
        assuntos_raw = src.get("assuntos", [])
        partes_raw = src.get("partes", [])
        movs_raw = src.get("movimentos", [])

        def parse_dt(value: str | None) -> datetime | None:
            if not value:
                return None
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None

        return Processo(
            numero_processo=numero,
            tribunal=src.get("tribunal", ""),
            grau=src.get("grau"),
            data_ajuizamento=parse_dt(src.get("dataAjuizamento")),
            data_ultima_atualizacao=parse_dt(src.get("dataHoraUltimaAtualizacao")),
            nivel_sigilo=nivel_sigilo,
            classe_codigo=classe.get("codigo"),
            classe_nome=classe.get("nome"),
            assuntos=[
                Assunto(
                    codigo=a.get("codigo", 0),
                    nome=a.get("nome", ""),
                    principal=a.get("principal", False),
                )
                for a in assuntos_raw
            ],
            orgao_julgador=OrgaoJulgador(
                codigo=orgao.get("codigo"),
                nome=orgao.get("nome", ""),
                codigo_municipio_ibge=orgao.get("codigoMunicipioIBGE"),
            )
            if orgao
            else None,
            partes=[
                Parte(
                    nome=p.get("nome", ""),
                    tipo=p.get("tipo", {}).get("nome", ""),
                    polo=p.get("polo"),
                )
                for p in partes_raw
            ],
            movimentacoes=[
                Movimentacao(
                    codigo=m.get("codigo"),
                    nome=m.get("nome", ""),
                    data_hora=parse_dt(m.get("dataHora"))
                    or datetime.min.replace(tzinfo=timezone.utc),
                    complementos=m.get("complementosTabelados", []),
                    grau=src.get("grau"),
                )
                for m in sorted(movs_raw, key=lambda x: x.get("dataHora", ""), reverse=True)
            ],
            formato=src.get("formato", {}).get("nome") if src.get("formato") else None,
            sistema=src.get("sistema", {}).get("nome") if src.get("sistema") else None,
        )


__all__ = ["DataJudClient"]
