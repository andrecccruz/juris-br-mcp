<!-- mcp-name: io.github.andrecccruz/juris-br-mcp -->

<p align="center">
  <img src="assets/banner.svg" width="800" alt="Juris BR MCP">
</p>

<p align="center">
  <strong>Conecte qualquer assistente de IA ao DataJud CNJ e ao DJEN - processos, andamentos de todas as instâncias, publicações e intimações, partes, monitoramento e prazos em dias úteis.</strong>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-1a7a4a?logo=python&logoColor=white" alt="Python 3.10+"></a>
  <a href="https://github.com/andrecccruz/juris-br-mcp/actions/workflows/ci.yml"><img src="https://github.com/andrecccruz/juris-br-mcp/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/licenca-MIT-4fc3f7?labelColor=001f5b" alt="Licença MIT"></a>
  <a href="https://modelcontextprotocol.io"><img src="https://img.shields.io/badge/MCP-compatível-7c3aed" alt="MCP Compatível"></a>
</p>

<p align="center">
  <a href="#o-que-é">O que é</a> ·
  <a href="#ferramentas-disponíveis">Ferramentas</a> ·
  <a href="#instalação">Instalação</a> ·
  <a href="#configuração-por-cliente-mcp">Configuração</a> ·
  <a href="#roadmap">Roadmap</a> ·
  <a href="#créditos">Créditos</a>
</p>

> **Baseado em [mcp-juridico-brasil](https://github.com/DeHor-Labs/mcp-juridico-brasil), de Nikolas de Hor (MIT).** O juris-br-mcp é um projeto independente que parte dele e acrescenta a integração com o DJEN, consolidação das instâncias do DataJud, detecção de respostas parciais do DataJud, validação do dígito verificador CNJ e persistência de monitoramento. Detalhes no [CHANGELOG](CHANGELOG.md).

---

## O que é

`juris-br-mcp` conecta assistentes de IA, escritórios de advocacia e sistemas de gestão processual a duas fontes públicas do CNJ:

- **DataJud** - base unificada de dados judiciais, com **92 siglas de tribunais cadastradas** em todas as justiças (Federal, Estadual, do Trabalho, Militar, Eleitoral e Superior). Traz metadados e movimentações. Estar cadastrado não garante que o DataJud tenha dados daquele tribunal: o volume depende do que cada tribunal envia ao CNJ.
- **DJEN** (Diário de Justiça Eletrônico Nacional) - traz o **texto** das publicações e intimações, as **partes** e os **advogados com OAB**, que o DataJud não fornece.

A proposta é ser uma vertical processual: transformar consultas judiciais fragmentadas em **tools seguras, componíveis e prontas para agentes** - com cálculo de prazos em dias úteis conforme o CPC, monitoramento de andamentos e acesso ao Domicílio Judicial Eletrônico.

---

## Ferramentas disponíveis

O servidor registra **11 tools** e **1 resource** (ver `src/juris_br_mcp/server.py`).

### Consulta e monitoramento de processos

| Ferramenta | Descrição | Fonte |
|------------|-----------|-------|
| `buscar_processo_por_numero` | Consulta completa de processo pelo número CNJ (NNNNNNN-DD.AAAA.J.TT.OOOO, com dígito verificador conferido). Consolida todas as instâncias (1º grau, 2º grau...), marca o grau de cada movimentação, alerta quando o DataJud está desatualizado ou respondeu de forma parcial e completa partes e advogados pelo DJEN | DataJud CNJ + DJEN |
| `listar_movimentacoes` | Histórico de andamentos de todas as instâncias, do mais recente ao mais antigo | DataJud CNJ |
| `resumir_andamento` | Dados do processo mais instrução de resumo para o modelo de linguagem | DataJud CNJ |
| `monitorar_processo` | Informa se houve atualização desde uma data e a data da última atualização (polling, sem gravar snapshot) | DataJud CNJ |
| `listar_processos_monitorados` | Lista processos com snapshot gravado (memória e disco). Nesta versão nenhuma tool de consulta grava snapshot, então a lista normalmente vem vazia | Local |

### Publicações e intimações (DJEN)

API pública do Diário de Justiça Eletrônico Nacional (Comunica PJe/CNJ), sem chave. Somente leitura, sem efeito jurídico.

| Ferramenta | Descrição | Fonte |
|------------|-----------|-------|
| `buscar_comunicacoes_djen` | Publicações e intimações por OAB, advogado, parte, número do processo, tribunal e período. Traz o texto da publicação, partes, advogados com OAB, link do documento e URL da certidão em PDF | DJEN |
| `processos_por_parte_djen` | Descobre processos de uma pessoa ou empresa pelo nome, agrupando as publicações por número. Só encontra processos que tiveram publicação no DJEN; homônimos podem aparecer | DJEN |

> **DataJud x DJEN:** o DataJud traz metadados e movimentações, mas não traz partes nem o texto dos atos. O DJEN traz o texto das publicações, as partes e os advogados. Os dois se complementam.

### Cálculo de prazos processuais

| Ferramenta | Descrição | Referência |
|------------|-----------|------------|
| `calcular_proximo_prazo` | Cálculo de prazo em dias úteis com recesso forense e feriados nacionais (art. 219, 220 e 224 CPC). Feriados estaduais só entram com `uf` informada | Offline com `data_intimacao_iso`; sem ela, consulta o DataJud para usar a última movimentação |

### Referência de tribunais

| Ferramenta | Descrição | Fonte |
|------------|-----------|-------|
| `listar_tribunais` | Lista as 92 siglas cadastradas no servidor (Portaria CNJ 160/2020) | Offline |

### Domicílio Judicial Eletrônico (opcional)

Exigem credenciais próprias do DJe (`DJE_CLIENT_ID`, `DJE_CLIENT_SECRET`, `DJE_BEHALF_OF_CPF`).

| Ferramenta | Descrição | Fonte |
|------------|-----------|-------|
| `listar_intimacoes` | Lista comunicações recebidas no DJe. Somente leitura; conteúdo de intimações sigilosas é suprimido | DJe (API Comunica) |
| `confirmar_leitura_intimacao` | Confirma leitura de intimação. **Tem efeito jurídico real e inicia prazo.** Funciona em dry-run por padrão e só confirma com `confirmar=True` e `DJE_PERMITIR_CONFIRMACAO_LEITURA=true` | DJe (API Comunica) |

### Resource MCP

| Resource | Descrição |
|----------|-----------|
| `processo://{numero}/snapshot` | Lê o snapshot gravado de um processo, se existir. Como `buscar_processo_por_numero` e `monitorar_processo` não gravam snapshot, nesta versão ele responde que não há snapshot disponível |

---

## Instalação

Pré-requisito: [uv](https://docs.astral.sh/uv/) (gerenciador de pacotes Python).

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Direto do GitHub (sem clonar)

O `uvx` baixa e executa o servidor em ambiente isolado:

```bash
uvx --from git+https://github.com/andrecccruz/juris-br-mcp juris-br-mcp
```

Para atualizar para a versão mais recente: `uvx --refresh --from git+https://github.com/andrecccruz/juris-br-mcp juris-br-mcp`.

### A partir do código-fonte

```bash
git clone https://github.com/andrecccruz/juris-br-mcp.git
cd juris-br-mcp
uv sync
uv run juris-br-mcp
```

---

## Configuração por cliente MCP

A variável `DATAJUD_API_KEY` é opcional: por padrão o servidor usa a chave pública vigente divulgada pelo CNJ em [datajud-wiki.cnj.jus.br](https://datajud-wiki.cnj.jus.br/api-publica/acesso/). Como o CNJ pode trocá-la a qualquer momento, use a variável para substituí-la quando necessário. O DJEN não exige chave.

### Claude Desktop

Em **Configurações → Desenvolvedor → Editar configuração**, ou direto no arquivo `%APPDATA%\Claude\claude_desktop_config.json` (Windows) / `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "juris-br": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/andrecccruz/juris-br-mcp", "juris-br-mcp"]
    }
  }
}
```

Usando um clone local (recomendado se você for alterar o código):

```json
{
  "mcpServers": {
    "juris-br": {
      "command": "uv",
      "args": ["--directory", "C:\\caminho\\para\\juris-br-mcp", "run", "juris-br-mcp"]
    }
  }
}
```

> **Windows:** se o Claude Desktop não encontrar `uv`/`uvx`, use o caminho completo do executável, por exemplo `C:\\Users\\SEU_USUARIO\\.local\\bin\\uvx.exe`.

Feche o Claude Desktop por completo (inclusive o ícone na bandeja do sistema) e abra de novo. O servidor aparece como **running** na aba Desenvolvedor.

### Claude Code (CLI)

```bash
claude mcp add juris-br -- uvx --from git+https://github.com/andrecccruz/juris-br-mcp juris-br-mcp
```

### Cursor / `.mcp.json`

Crie ou edite `.cursor/mcp.json` (ou `.mcp.json` na raiz do projeto):

```json
{
  "mcpServers": {
    "juris-br": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/andrecccruz/juris-br-mcp", "juris-br-mcp"]
    }
  }
}
```

---

## Variáveis de ambiente

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `DATAJUD_API_KEY` | Substitui a chave pública padrão do DataJud CNJ | chave pública vigente do CNJ |
| `JURIDICO_LOG_LEVEL` | Nível de log: `DEBUG`, `INFO`, `WARNING` | `INFO` |
| `JURIDICO_SNAPSHOT_DIR` | Diretório dos snapshots gravados. Use `memoria` para não gravar em disco | `~/.juris-br-mcp/snapshots` |
| `JURIDICO_HTTP_TIMEOUT` | Timeout em segundos para chamadas HTTP | `30` |
| `DATAJUD_TIMEOUT` | Timeout em segundos das consultas ao DataJud (sobrecarregado, ele leva 30-45s) | `60` |

Veja todas em [`.env.example`](.env.example).

---

## Uso sem cliente MCP

As tools são funções Python comuns e podem ser chamadas direto, sem passar por um modelo de linguagem (sem gastar tokens). Veja [`examples/consulta_direta.py`](examples/consulta_direta.py):

```bash
uv run python examples/consulta_direta.py processo 0701300-13.2011.8.26.0020
uv run python examples/consulta_direta.py oab 123456 SP 2026-11-01
uv run python examples/consulta_direta.py parte "NOME COMPLETO DA PARTE" TRT2
```

---

## Arquitetura

```
Claude / GPT / Cursor / qualquer cliente MCP
              |
              | Model Context Protocol (stdio)
              v
         juris-br-mcp
              |
    +---------+---------+-----------+----------+-----------+
    |         |         |           |          |           |
 Processos  Movim.   Resumo    Monitoram.  Prazos    Publicações
    |         |         |           |          |           |
    v         v         v           v          v           v
 DataJud   DataJud   DataJud    DataJud   Calendário     DJEN
 + DJEN      CNJ       CNJ        CNJ      forense    (Comunica PJe)
 (partes)                                  offline
```

**Fontes de dados:**
- [DataJud CNJ](https://datajud-wiki.cnj.jus.br/) - base unificada de dados judiciais (Portaria CNJ 160/2020)
- [DJEN / Comunica PJe](https://comunica.pje.jus.br/) - publicações e intimações do Diário de Justiça Eletrônico Nacional (API pública)
- Calendário forense nacional e estadual - processado offline para cálculo de prazos (CPC art. 219/220/224)

**Confiabilidade do DataJud:** quando o cluster do DataJud está sobrecarregado, ele pode responder HTTP 200 com parte dos índices falhando. O juris-br-mcp detecta isso: um resultado parcial vazio é reportado como indisponibilidade (e não como "processo não encontrado"), e um resultado parcial com dados traz `alerta_resultado_incompleto`.

---

## Roadmap

- [x] **0.1.0** - Projeto original (mcp-juridico-brasil): processo, movimentações, resumo, monitoramento, prazos, tribunais e DJe
- [x] **0.2.0** - DJEN (publicações, partes, descoberta por nome), consolidação de instâncias, detecção de resposta parcial do DataJud, dígito verificador CNJ, persistência de snapshots
- [ ] Busca no DataJud por classe, órgão julgador, assunto e período
- [ ] Filtro de "outra parte" na descoberta por nome (ex.: ex-funcionário x empresa)
- [ ] Jurisprudência e súmulas (LexML)
- [ ] Cálculos judiciais com índices oficiais (BACEN/IBGE)

---

## Privacidade e LGPD

> **Atenção:** as tools de consulta processual acessam exclusivamente dados públicos disponibilizados pelo DataJud CNJ (Resolução CNJ 331/2020) e pelo DJEN; processos em **segredo de justiça** não são retornados. As tools do DJEN retornam nomes de partes publicados oficialmente; a busca por nome pode trazer homônimos e deve ser conferida antes de qualquer conclusão. As tools opcionais do DJe são diferentes: com credenciais do próprio advogado, acessam comunicações processuais não públicas recebidas no Domicílio Judicial Eletrônico, com o conteúdo de intimações sigilosas suprimido, e `confirmar_leitura_intimacao` pode produzir efeito jurídico. Nenhum dado processual é enviado a servidores do projeto: tudo roda no ambiente local do usuário. O uso das ferramentas é de responsabilidade do profissional habilitado, em conformidade com a LGPD (Lei 13.709/2018), a Resolução CNJ 647/2025 e a OAB Recomendação 001/2024. Estas ferramentas não constituem consultoria jurídica.

---

## Contribuindo

Contribuições são bem-vindas! Veja [CONTRIBUTING.md](CONTRIBUTING.md).

```bash
git clone https://github.com/andrecccruz/juris-br-mcp.git
cd juris-br-mcp
uv sync --extra dev

uv run pytest
uv run ruff check src tests
uv run mypy src
```

Cada módulo segue o padrão `client.py` + `tools.py`, tornando simples adicionar novas fontes processuais.

---

## Créditos

O juris-br-mcp é derivado do [mcp-juridico-brasil](https://github.com/DeHor-Labs/mcp-juridico-brasil), criado por **Nikolas de Hor** e distribuído sob licença MIT. A arquitetura, as tools de prazo, o DJe e a base do cliente DataJud vêm do projeto original.

---

## Licença

MIT - veja [LICENSE](LICENSE) para detalhes.
