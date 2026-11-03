# juris-br-mcp

Servidor MCP para consulta processual brasileira. Liga o Claude (ou qualquer cliente compatível com o Model Context Protocol) a duas bases públicas do CNJ:

- **DataJud** - dados e andamentos dos processos de 92 tribunais;
- **DJEN** (Diário de Justiça Eletrônico Nacional) - texto das publicações e intimações, partes e advogados.

Com ele, dá para pedir em linguagem natural coisas como *"quais publicações saíram hoje para a OAB 123456/SP?"*, *"traga o andamento do processo 0701300-13.2011.8.26.0020"* ou *"encontre processos em que a empresa X é parte no TRT2"*.

Tudo roda na sua máquina, usando apenas APIs públicas e gratuitas. Não há cadastro nem chave para obter.

---

## O que ele faz

**Processos (DataJud + DJEN)**

- `buscar_processo_por_numero` - dados completos do processo a partir do número CNJ. Reúne todas as instâncias (1º grau, 2º grau...) numa linha do tempo única, indica o grau de cada andamento e completa partes e advogados com as publicações do DJEN. Avisa quando o DataJud está desatualizado ou respondeu de forma incompleta.
- `listar_movimentacoes` - andamentos de todas as instâncias, do mais recente para o mais antigo.
- `resumir_andamento` - dados do processo prontos para o assistente resumir.
- `monitorar_processo` - diz se o processo teve atualização desde uma data.
- `listar_processos_monitorados` - processos com dados salvos localmente.

**Publicações e intimações (DJEN)** - somente leitura, sem efeito jurídico

- `buscar_comunicacoes_djen` - publicações por OAB, advogado, parte, número do processo, tribunal e período, com o texto completo, partes, advogados, link do documento e certidão em PDF.
- `processos_por_parte_djen` - descobre os processos de uma pessoa ou empresa pelo nome.

**Prazos e apoio**

- `calcular_proximo_prazo` - prazo em dias úteis com feriados e recesso forense (arts. 219, 220 e 224 do CPC).
- `listar_tribunais` - siglas aceitas pelas demais ferramentas.

**Domicílio Judicial Eletrônico** - opcional, exige credenciais próprias do DJe

- `listar_intimacoes` - comunicações recebidas no Domicílio.
- `confirmar_leitura_intimacao` - **tem efeito jurídico real e inicia prazo.** Funciona em modo de simulação por padrão e só confirma com dupla autorização explícita.

### Limites que vale conhecer

- O DataJud **não informa partes** e pode ter de 1 a 7 dias de atraso em relação ao portal do tribunal. As partes vêm do DJEN.
- O DJEN só tem processos que tiveram **alguma publicação**. A busca por nome pode trazer **homônimos**: confira partes e advogados antes de concluir.
- Processos em **segredo de justiça** não aparecem em nenhuma das duas bases.
- Quando o DataJud está sobrecarregado, as consultas ficam lentas (até alguns minutos). Nesses casos, o servidor informa a indisponibilidade em vez de responder "processo não encontrado".

---

## Instalação

É preciso ter o [uv](https://docs.astral.sh/uv/) instalado:

```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Depois, escolha uma das formas abaixo.

**Direto do GitHub** - o `uvx` baixa e executa o servidor, sem clonar nada:

```bash
uvx --from git+https://github.com/andrecccruz/juris-br-mcp juris-br-mcp
```

**Clonando o repositório** - melhor se você pretende alterar o código:

```bash
git clone https://github.com/andrecccruz/juris-br-mcp.git
cd juris-br-mcp
uv sync
```

---

## Ligando ao Claude

### Claude Desktop

Abra **Configurações → Desenvolvedor → Editar configuração** e acrescente o servidor em `mcpServers`:

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

Se você clonou o repositório, aponte para a pasta dele:

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

Feche o Claude Desktop por completo (inclusive pelo ícone perto do relógio) e abra de novo. O servidor deve aparecer como **running** na aba Desenvolvedor.

> No Windows, se o Claude Desktop não encontrar o `uv` ou o `uvx`, informe o caminho completo, por exemplo `C:\\Users\\SEU_USUARIO\\.local\\bin\\uv.exe`.

### Claude Code

```bash
claude mcp add juris-br -- uvx --from git+https://github.com/andrecccruz/juris-br-mcp juris-br-mcp
```

### Outros clientes

Qualquer cliente MCP que execute servidores via `stdio` funciona com o mesmo comando e os mesmos argumentos do Claude Desktop.

---

## Usando sem o Claude

As ferramentas são funções Python comuns. Dá para chamá-las de scripts, planilhas ou agendadores sem passar por um modelo de linguagem, e portanto sem gastar tokens. O arquivo [`examples/consulta_direta.py`](examples/consulta_direta.py) mostra como:

```bash
uv run python examples/consulta_direta.py processo 0701300-13.2011.8.26.0020
uv run python examples/consulta_direta.py oab 123456 SP 2026-11-01
uv run python examples/consulta_direta.py parte "NOME COMPLETO DA PARTE" TRT2
```

A saída é o mesmo JSON que o Claude recebe.

---

## Configurações opcionais

Nenhuma é obrigatória. A lista completa está em [`.env.example`](.env.example).

| Variável | Para que serve | Padrão |
|----------|----------------|--------|
| `DATAJUD_API_KEY` | Trocar a chave pública do DataJud, caso o CNJ a altere ([wiki do DataJud](https://datajud-wiki.cnj.jus.br/api-publica/acesso/)) | chave pública atual |
| `DATAJUD_TIMEOUT` | Tempo máximo de espera por consulta ao DataJud, em segundos | `60` |
| `JURIDICO_SNAPSHOT_DIR` | Pasta dos dados de monitoramento (`memoria` para não gravar em disco) | `~/.juris-br-mcp/snapshots` |
| `JURIDICO_LOG_LEVEL` | Nível de detalhe dos logs | `INFO` |

---

## Fontes

- [DataJud](https://datajud-wiki.cnj.jus.br/) - API pública do CNJ (Portaria CNJ 160/2020).
- [DJEN / Comunica PJe](https://comunica.pje.jus.br/) - API pública do Diário de Justiça Eletrônico Nacional.
- Calendário forense nacional e estadual, calculado localmente.

---

## Privacidade e responsabilidade

As consultas usam apenas dados públicos do DataJud e do DJEN, e nada é enviado a servidores deste projeto. As ferramentas opcionais do Domicílio Judicial Eletrônico usam credenciais do próprio advogado, e `confirmar_leitura_intimacao` pode produzir efeito jurídico.

O uso é de responsabilidade do profissional habilitado, em conformidade com a LGPD (Lei 13.709/2018), a Resolução CNJ 647/2025 e a Recomendação OAB 001/2024. Estas ferramentas não constituem consultoria jurídica.

---

## Créditos

Este projeto é derivado do [mcp-juridico-brasil](https://github.com/DeHor-Labs/mcp-juridico-brasil), criado por **Nikolas de Hor** e distribuído sob licença MIT. A estrutura do servidor, o cálculo de prazos, a integração com o Domicílio Judicial Eletrônico e a base do cliente DataJud vêm do projeto original. As mudanças feitas aqui estão no [CHANGELOG](CHANGELOG.md).

## Licença

MIT - veja [LICENSE](LICENSE).
