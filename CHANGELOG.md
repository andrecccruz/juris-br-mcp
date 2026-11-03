# Changelog

Todas as mudanças notáveis neste projeto serão documentadas aqui.

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
versionamento seguindo [Semantic Versioning](https://semver.org/lang/pt-BR/).

## [Unreleased]

## [0.2.0] - 2026-11-03

Primeira versão do **juris-br-mcp**, derivado de
[mcp-juridico-brasil](https://github.com/DeHor-Labs/mcp-juridico-brasil) 0.1.0, de Nikolas de Hor
(licença MIT). Pacote Python renomeado de `mcp_juridico_brasil` para `juris_br_mcp` e comando
de `mcp-juridico-brasil` para `juris-br-mcp`.

### Adicionado

- Módulo `djen` - Diário de Justiça Eletrônico Nacional (API pública Comunica PJe, sem chave):
  - `buscar_comunicacoes_djen` - publicações/intimações por OAB, advogado, parte, número do
    processo, tribunal e período, com texto limpo (HTML convertido), partes, advogados (OAB),
    link do documento e URL da certidão em PDF.
  - `processos_por_parte_djen` - descoberta de processos pelo nome da parte, agrupando as
    publicações por número de processo.
- `buscar_processo_por_numero` passa a trazer `partes_djen` (partes e advogados das publicações
  do DJEN), já que a API pública do DataJud não informa partes. Desligável com
  `incluir_partes_djen=False`.
- Campo `instancias` em `Processo` e campo `grau` em cada movimentação.
- Bloco `atualizacao` com dias desde a última atualização no DataJud e alerta acima de 7 dias.
- Validação do dígito verificador do número CNJ (módulo 97), com mensagem indicando o dígito
  esperado.
- Configuração `DATAJUD_TIMEOUT` (padrão 60s).
- `examples/consulta_direta.py` - uso das tools como biblioteca Python, sem cliente MCP.

### Corrigido

- DataJud: a busca pedia `size: 1` e devolvia uma instância arbitrária quando o processo tem
  registros em mais de um grau (ex.: G1 e G2). Agora consolida todas: metadados da instância
  atualizada mais recentemente e movimentações de todas.
- DataJud: respostas HTTP 200 com shards falhos (cluster sobrecarregado) eram tratadas como
  completas, gerando falso "processo não encontrado". Agora resultado parcial vazio gera
  `JuridicoAPIError`, parcial com dados traz `alerta_resultado_incompleto`, e respostas parciais
  não entram no cache.
- DataJud: HTTP 429 e timeout viram `JuridicoAPIError` com mensagem clara; se o tribunal deduzido
  do número CNJ está indisponível, não varre os outros 91 índices.
- `HTTPClient` era recriado a cada consulta, anulando cache TTL e rate limit. Agora há um cliente
  persistente por tribunal (recriado automaticamente se o event loop mudar).

### Alterado

- Snapshots de monitoramento persistem em `~/.juris-br-mcp/snapshots` por padrão
  (`JURIDICO_SNAPSHOT_DIR=memoria` desliga o disco); `listar_processos_monitorados` inclui os
  snapshots gravados em disco.
- Fixtures de teste usam números CNJ com dígito verificador válido.

## [0.1.0] - 2026-06-22

Versão do projeto original (mcp-juridico-brasil, Nikolas de Hor), mantida aqui como histórico.

### Adicionado

#### Fase 1 - Consulta processual via DataJud CNJ

- `buscar_processo_por_numero` - consulta completa de um processo pelo número CNJ unificado
  (NNNNNNN-DD.AAAA.J.TT.OOOO), retornando dados cadastrais, classe, assunto, órgão julgador,
  valor da causa e situação atual. Cobertura de 91 tribunais (STF, STJ, TJs, TRFs, TRTs e
  especializados).
- `listar_movimentacoes` - lista as movimentações processuais com data, código CNJ de movimento
  e complementos. Suporta cursor de navegação por offset e filtro por período.
- `resumir_andamento` - retorna dados do processo mais instrução de resumo estruturado para o
  modelo de linguagem: partes, fase atual, últimas movimentações e próximos passos relevantes.
- `monitorar_processo` - verifica atualizações desde uma data de referência (polling com snapshot
  em memória), retornando flag de atualização e diff de movimentações novas.
- `listar_tribunais` - retorna a lista completa dos 91 tribunais cobertos pela API DataJud com
  suas siglas (Portaria CNJ 160/2020). Use as siglas retornadas no parâmetro `tribunal` das
  demais tools.

#### Fase 2 - Cálculo de prazo e resources de monitoramento

- `calcular_proximo_prazo` - calcula o próximo prazo processual a partir de uma data-base,
  considerando dias úteis, feriados nacionais, estaduais e recessos forenses configuráveis por
  tribunal (art. 219, 220 e 224 do CPC). Usa `workalendar` para calendário brasileiro. Retorna
  data de vencimento, dias úteis percorridos e lista de dias não computados com justificativa.
- `listar_processos_monitorados` - lista os números de processos que possuem snapshot salvo na
  sessão MCP atual. Use o resource `processo://{numero}/snapshot` para ler os dados completos.
- Resource `processo://{numero_processo}/snapshot` - retorna o último snapshot capturado por
  `buscar_processo_por_numero` ou `monitorar_processo` para o processo informado. O estado é
  mantido em memória da sessão; configure `JURIDICO_SNAPSHOT_DIR` para persistência em arquivo.

[Unreleased]: https://github.com/andrecccruz/juris-br-mcp/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/andrecccruz/juris-br-mcp/releases/tag/v0.2.0
[0.1.0]: https://github.com/DeHor-Labs/mcp-juridico-brasil/releases/tag/v0.1.0
