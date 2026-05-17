# Arquitetura do SCLME

Marco 10.6 - Consolidacao Arquitetural Pre-Produto — Concluido.

Data de conclusao: 2026-05-16

## Objetivo

Este documento registra a arquitetura atual do SCLME, seus pontos fortes, dividas tecnicas e riscos para crescimento futuro.

A decisao atual e nao migrar imediatamente para Django. Antes disso, o projeto deve reduzir acoplamento, separar responsabilidades e preparar uma arquitetura mais limpa para evolucao.

## Stack Atual

| Camada | Tecnologia | Papel |
| --- | --- | --- |
| Interface | Streamlit | WebApp, formularios, dashboards, tabelas e navegacao |
| Banco | SQLite | Persistencia local simples e portavel |
| Processamento | Pandas | Leitura, transformacao e apresentacao tabular |
| Excel I/O | OpenPyXL | Leitura e escrita de arquivos `.xlsx` |
| Graficos | Plotly | Visualizacoes interativas no dashboard |
| Testes | Pytest | Testes de parsers, importadores, engines, exportadores e helpers |

## Estrutura Atual de Pastas

```text
main.py                  Entrada do app e navegacao
pages/                   Paginas Streamlit
app/                     Sessao, contexto e componentes ligados a UI
core/                    Regras e modulos reutilizaveis
  auth/                  Permissoes basicas
  engine/                Status, comparacao, preview, emissao inicial
  exporters/             Exportacoes Excel
  importers/             Importadores de Lista, ID, arquivos e cadastro
  parsers/               Parsers de codigos e arquivos
  repositories/          Acesso ao banco por entidade (implementado no Marco 10.6)
  services/              Orquestracao de regras de aplicacao (implementado no Marco 10.6)
db/                      Conexao SQLite e banco local
scripts/                 Inicializacao e migracoes simples
tests/                   Testes automatizados (570 testes — Marco 10.6)
docs/                    Documentacao tecnica, produto e ADRs
```

## Papel de Cada Camada Atual

### `pages/`

Contem as telas Streamlit:

- dashboard;
- importacao;
- comparacao ID x Lista;
- cadastro manual;
- pesquisa documental.

Hoje as paginas fazem mais do que deveriam: capturam input, exibem output, acessam banco, montam payloads e aplicam parte da regra de aplicacao.

O Marco 10.7 refatora `pages/4_CadastroManual.py` para introduzir entrada segmentada de codigo, campos derivados somente leitura, preview de confirmacao e suporte a lote, sem alterar o `CadastroService`.

Diretriz futura: paginas devem funcionar como camada de UI/controller leve.

### `app/`

Concentra estado de sessao, contrato ativo e contexto lateral. Depende diretamente de Streamlit.

Diretriz futura: manter aqui apenas elementos ligados a interface, sessao e adaptadores de UI.

### `core/`

Contem a maior parte da regra reutilizavel:

- parsers;
- importadores;
- engines;
- exportadores;
- permissoes basicas;
- formatacao e busca.

E a camada mais importante para preservar em uma futura migracao.

Diretriz futura: `core/` nao deve depender de Streamlit.

### `db/`

Contem `connection.py`, que centraliza conexao SQLite.

Diretriz futura: acesso ao banco deve passar por repositories, evitando SQL direto em paginas.

### `scripts/`

Contem `init_db.py`, que cria tabelas e faz migracoes simples/idempotentes.

Diretriz futura: caso o projeto avance para Django ou PostgreSQL, esse papel deve ser substituido por migrations reais.

### `core/repositories/`

Implementado no Marco 10.6. Cada repository encapsula o acesso ao banco para uma entidade:

- `ContractRepository`;
- `ImportacaoRepository`;
- `DocumentoRepository`;
- `RevisaoRepository`.

### `core/services/`

Implementado no Marco 10.6. Cada service orquestra regras de aplicacao sem depender de Streamlit:

- `ContractService`;
- `ImportacaoService`;
- `DocumentoService`;
- `CadastroService`;
- `DashboardService`.

### `tests/`

Contem testes de parsers, importadores, engines, exportadores, auth, repositories e services.
Suite atual: 570 testes.

## Pontos Fortes Atuais

- MVP funcional de ponta a ponta.
- Fluxo real de importacao, comparacao, dashboard e consulta documental.
- Parsers isolados e testaveis.
- Importadores robustos e idempotentes em pontos importantes.
- Engines ja centralizam regras relevantes.
- Exportadores independentes da UI.
- Testes automatizados em areas criticas.
- Separacao inicial de `core/`.
- Modularizacao parcial suficiente para refatoracao incremental.
- Documentacao inicial de produto, arquitetura e ADR.

## Dividas Tecnicas Identificadas

### SQL Direto em `main.py` e `pages/` (parcialmente resolvido)

No Marco 10.6, `pages/1_Dashboard.py`, `pages/4_CadastroManual.py` e `pages/5_Documento.py` foram refatoradas para consumir services e repositories.

Ainda com SQL direto:

- `main.py`;
- `pages/2_Importacao.py`;
- `app/session.py`.

Isso dificulta testes, manutencao e migracao futura.

### Paginas Fazendo Papel de Controller + Service + Repository

Algumas paginas capturam input, validam estado, consultam banco, aplicam regra e renderizam resultado. Esse acoplamento aumenta custo de evolucao.

### Dependencia Forte de `st.session_state`

O cadastro manual e a selecao de contrato dependem bastante de `st.session_state`. Isso e natural em Streamlit, mas precisa ficar restrito a camada de UI.

### Dependencia de `pandas.DataFrame` Como Contrato Interno

DataFrames sao uteis para importacao, exportacao e visualizacao, mas nao devem virar contrato universal de dominio. Services futuros devem poder retornar estruturas mais explicitas quando apropriado.

### `core` Ainda Conhecendo SQLite Diretamente

Muitos modulos de `core` usam `get_connection()` e SQL diretamente. Isso e aceitavel no MVP, mas dificulta trocar banco ou reaproveitar regras em outra interface.

### Regras de Fallback/Enriquecimento em Paginas

Fallback de trecho, disciplina, status e enriquecimento de documento ainda aparecem em paginas, especialmente na pesquisa documental.

### `sys.path.insert` em Varios Arquivos

Esse padrao facilita execucao local, mas indica que o projeto ainda nao esta empacotado de forma limpa.

### Banco Demo e Banco Operacional Pouco Separados

O banco SQLite pode ser usado como demo, piloto ou operacao local. Essa distincao precisa ficar mais clara para evitar confusao.

### Ausencia de Migrations Reais

`scripts/init_db.py` resolve a fase atual, mas nao substitui sistema de migrations para ambiente corporativo.

### Multiusuario e Concorrencia Nao Resolvidos

SQLite + Streamlit atendem ao MVP e piloto controlado, mas nao resolvem gravacoes simultaneas robustas.

## Riscos Para Futura Migracao

- SQLite usa funcoes e padroes especificos, como `julianday`, `last_insert_rowid()`, `INSERT OR IGNORE` e `INSERT OR REPLACE`.
- `scripts/init_db.py` nao equivale a migrations Django.
- `auth/session` dependem de Streamlit.
- Falta camada formal de DTOs/objetos de dominio.
- Logica de negocio ainda aparece misturada com interface.
- Parte do `core` depende diretamente do banco.
- DataFrames aparecem como estrutura de retorno em pontos importantes.
- Falta uma fronteira clara entre UI, service, repository e dominio.

## Diretrizes Arquiteturais

- Nao adicionar features grandes sem reduzir acoplamento estrutural.
- Tirar SQL direto das paginas gradualmente.
- Criar repositories antes de trocar banco.
- Criar services antes de aumentar fluxos de produto.
- Manter regras de negocio fora de Streamlit.
- Manter Pandas em importacao/exportacao/visualizacao, mas evitar dependencia universal.
- Preservar testes existentes.
- Toda extracao de service/repository deve manter comportamento atual.

## Estrategia — Progresso do Marco 10.6

| Passo | Descricao | Status |
| --- | --- | --- |
| 1 | Criar camada de repositories | Concluido |
| 2 | Mover consultas SQL das paginas para repositories | Concluido (parcial: paginas 1, 4, 5) |
| 3 | Criar services para orquestrar regras de aplicacao | Concluido |
| 4 | Reduzir dependencia direta de `st.session_state` | Parcial |
| 5 | Separar auth puro de auth UI | Pendente |
| 6 | Reduzir retorno obrigatorio em DataFrame onde nao for necessario | Pendente |
| 7 | Remover `sys.path.insert` gradualmente | Pendente |
| 8 | Depois reavaliar Django | Pendente |

## Conclusao

O Marco 10.6 foi concluido. A camada de repositories e services esta implementada e coberta por testes (suite com 570 testes passando). As paginas de maior complexidade foram refatoradas para consumir exclusivamente essas camadas.

O proximo passo e retomar os marcos funcionais (Marco 11 em diante) com a base arquitetural consolidada.

