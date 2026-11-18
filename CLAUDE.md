# SCLME — Sistema de Controle de Lista Mestra de Projetos Executivos

## O que é este projeto

Sistema local de controle documental de engenharia para a **Linha 15 — Metrô de São Paulo**.
Substitui uma planilha Excel manual por uma aplicação Streamlit + SQLite rastreável e auditável.

**Domínio:** Documentos técnicos de obras de metrô (Desenhos, Memoriais, Relatórios, Índices etc.).  
**Usuário principal:** Gestor de documentação / engenheiro responsável pelo controle da Lista Mestra.

---

## Modelo de trabalho e regras permanentes

- **Divisão de papéis:** Claude Code atua como analista/arquiteto/planejador/revisor e autor dos prompts de implementação; o **Codex é o implementador** (código, testes, commits); o **usuário é a autoridade final** sobre domínio, escopo, commits e push.
- **Verificação antes de aceitar:** relatórios de implementação nunca são aceitos sem conferência no repositório real (git status/diff, grep, leitura dos arquivos, rodar a suíte).
- **Governança em `cognitive_arch_V2/`:** memória de execução (fases, blocks, estado) local ao projeto e **ignorada pelo Git — nunca versionar/commitar** (idem `cognitive-arch/` v1, histórica). O status ao vivo de marcos/blocks vive em `docs/ROADMAP.md` + `cognitive_arch_V2` (STATE/NEXT/BLOCK_LOG), não nesta CLAUDE.md.
- **Git:** pela esteira, commit e **push automáticos por Block conferido** (suíte verde, sem segredos e sem dados de `entrada/`), conforme a seção "Autorização atual" do `cognitive_arch_V2/control-room/ESTEIRA.md`. Nunca force-push. Mensagens em português; nunca versionar `db/sclme.db`, dados reais/confidenciais, ou as pastas de cognitive arch.
- **Banco único:** o app usa sempre `db/sclme.db` — não há mais "modo demo" / `SCLME_DB_MODE` (criado e depois removido por decisão de produto).
- **Camadas:** `core/` nunca importa Streamlit; regra de negócio em `engine`/`services`/`repositories`; páginas apenas capturam input, chamam services e exibem — **sem SQL em páginas**.
- **Esteira, worktrees e agentes (decisão D-012):** o checkout principal é C:\Sistema de Controle Lista Mestra. Vários agentes Codex podem rodar em paralelo quando mexem em arquivos diferentes. Se houver risco de colisão, cada um trabalha numa worktree própria (`../sclme-wt-<block>`, branch `wt/<block>`), que o Claude integra depois. As regras operacionais estão em `cognitive_arch_V2/control-room/ESTEIRA.md`. Antes de implementar, confirmar diretório, branch e git status.
---

## Como rodar

```bash
# 1. Ativar ambiente virtual (criar na primeira vez: python -m venv .venv)
.venv\Scripts\activate          # Windows

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Inicializar o banco (apenas na primeira vez, ou após limpar o db/)
python scripts/init_db.py

# 4. Subir a aplicação
streamlit run main.py
```

## Como rodar os testes

```bash
pytest tests/ -v
# Com cobertura:
pytest tests/ -v --cov=core --cov-report=term-missing
```

---

## Arquitetura

```
sclme/
├── main.py                     # Home page — grade de contratos com cards e métricas
├── pages/                      # Páginas Streamlit (multi-page app — ao lado do main.py)
│   ├── 1_Dashboard.py          # Dashboard de progresso por status e trecho
│   ├── 2_Importacao.py         # Upload de Excel + nomes.txt (com preview de arquivos)
│   ├── 3_Comparacao.py         # Comparação ID × Lista (ausentes, extras, divergências)
│   ├── 4_CadastroManual.py     # Cadastro manual: builder segmentado + revisão + GRD
│   └── 5_Documento.py          # Detalhe por documento: ficha, linha do tempo, arquivos, GRDs
├── core/
│   ├── parsers/                # Interpretação de códigos e nomes de arquivo
│   │   ├── base_parser.py      # Contrato (BaseParser, CodigoParseado, ErroDeparse)
│   │   ├── linha15_parser.py   # Parser da Linha 15 — Metrô SP
│   │   ├── registry.py         # Seleção automática de parser por contrato
│   │   ├── arquivo_parser.py   # Parser de nome de arquivo (CODIGO-REV-VER.ext)
│   │   └── codigo_builder.py   # Montagem/desmontagem de código Linha 15 (LINHA15_TIPOS, CLASSES)
│   ├── importers/              # Leitura de Excel e arquivos externos
│   │   ├── lista_importer.py   # Lista de Documentos → documentos + revisoes
│   │   ├── id_importer.py      # Índice de Documentos → documentos_previstos
│   │   └── arquivos_importer.py# nomes.txt → arquivos (vincula arquivo ao documento)
│   ├── engine/                 # Regras de negócio
│   │   ├── status.py           # Classificação de status, carregar_progresso, carregar_alertas
│   │   ├── comparacao.py       # Comparação ID × Lista (ResultadoComparacao)
│   │   ├── preview_arquivos.py # Preview dry-run de importação de arquivos
│   │   ├── disciplinas.py      # Tabela A1–Z2 de estruturas/disciplinas + SITUACOES
│   │   └── emissao_inicial.py  # Recalculo cronológico de EMISSÃO INICIAL por documento
│   ├── exporters/              # Geração de relatórios
│   └── auth/
│       └── permissions.py      # Perfis e permissões (can_perfil, can, require_permission)
├── app/
│   ├── session.py              # Estado de sessão: require_contrato, set_contrato_ativo
│   └── components/             # Widgets reutilizáveis (futuro)
├── db/
│   ├── connection.py           # Fábrica de conexões SQLite (FK + row_factory)
│   └── sclme.db                # Banco gerado localmente (não versionado)
├── scripts/
│   └── init_db.py              # Cria tabelas + migra colunas novas (idempotente)
└── tests/
    ├── test_parsers/
    ├── test_importers/
    └── test_engine/
```

### Camadas e responsabilidades

| Camada | Responsabilidade |
|--------|-----------------|
| `core/parsers` | Interpretação e validação de códigos documentais; `codigo_builder` monta/desmonta |
| `core/importers` | Leitura de fontes externas (Excel) |
| `core/engine` | Regras puras de domínio (status, ciclo documental, comparações, alertas, pendências) |
| `core/services` | Casos de uso / orquestração (Cadastro, Documento, Dashboard, GRD, Pendências, Importação) |
| `core/repositories` | Acesso a dados por agregado (Contrato, Documento, Revisão, Importação, GRD, Pendência) |
| `core/auth` | Perfis e permissões (`can_perfil` pura + `can` via session_state) |
| `api/` | Adapter público FastAPI (recebimento de GRD por token) — casca HTTP, sem regra de negócio |
| `app/session` | Contrato ativo na sessão (`require_contrato`, `set_contrato_ativo`) |
| `pages/` | Interface Streamlit — sem lógica de negócio; consome `core/` e `app/` |
| `db/` | Acesso ao SQLite via `get_connection()` |

---

## Padrão de código documental — Linha 15

Formato: `TIPO-LINHA.TRECHO.SUBTRECHO.UNIDADE-ETAPACLS-SEQUENCIAL`

Exemplo: `DE-15.25.00.00-6A1-1001`

| Campo | Exemplo | Regra |
|-------|---------|-------|
| TIPO | DE | 2–4 letras maiúsculas |
| LINHA | 15 | Sempre "15" neste contrato |
| TRECHO | 25 | 2 dígitos (19=Oratório, 23=São Mateus, 25=Ragueb Chohfi, 00=Geral) |
| SUBTRECHO | 00 | 2 dígitos |
| UNIDADE | 00 | 2 dígitos |
| ETAPA | 6 | 1 dígito |
| CLASSE | A | 1 letra maiúscula (tabela do MAN-10-201; códigos reais usam além de A–I, ex.: J, N, P) |
| SUBCLASSE | 1 | 1–2 dígitos |
| SEQUENCIAL | 1001 | 4 dígitos |

### Tipos documentais conhecidos

| Sigla | Descrição |
|-------|-----------|
| DE | Desenho |
| MC | Memorial de Cálculo |
| MD | Memorial Descritivo |
| RT | Relatório Técnico |
| ID | Índice de Documentos |
| ICS | Instrução de Serviço |
| PE | Procedimento Específico |
| MQ | Manual da Qualidade / Plano de Gestão |
| LM | Lista de Materiais |
| NS | Notas de Serviço |
| TC | Tabela de Coordenadas |

---

## Banco de dados (SQLite)

Sempre acesse via `db/connection.py` — nunca `sqlite3.connect()` diretamente.

```python
from db.connection import get_connection

with get_connection() as conn:
    rows = conn.execute("SELECT * FROM documentos").fetchall()
```

### Tabelas principais

| Tabela | Propósito |
|--------|-----------|
| `contratos` | Obras/contratos gerenciados |
| `documentos` | Documentos controlados (código base, sem revisão) |
| `revisoes` | Histórico de revisões — inclui `emissao_inicial` e `data_circular` |
| `documentos_previstos` | Escopo previsto (vindo do Índice de Documentos) |
| `arquivos` | Arquivos físicos/digitais — `objeto` imutável por arquivo |
| `grds` | GRDs legadas por revisão e setor (mantida por compatibilidade) |
| `grd_remessas` / `grd_itens` | GRD em lote — cabeçalho + itens com snapshot congelado, cópias A0–A4/Digital, token de recebimento (modelo operacional atual) |
| `importacoes` | Rastreabilidade de cada lote importado |
| `inconsistencias` | Erros/alertas detectados durante importações |
| `pendencias_dispensas` | Decisões humanas (resolvida/ignorada) sobre pendências calculadas ao vivo |

**Campos notáveis:**
- `documentos.disciplina` — código A1–Z2 da disciplina (chamado "ESTRUTURA" no Excel)
- `documentos.fase` — fase do projeto (ex: EXECUTIVO)
- `revisoes.emissao_inicial` — rótulo cronológico calculado: "EMISSÃO INICIAL", "REVISÃO 1"…, "REVISÃO FINAL"
- `revisoes.emissao_circular` — Nº Circular; `revisoes.analise_circular` — Análise Interna
- `arquivos.objeto` — Objeto no momento do registro; imutável (histórico preservado)

---

## Parsers — como adicionar novo contrato

1. Crie `core/parsers/meu_contrato_parser.py` herdando `BaseParser`
2. Implemente: `nome`, `descricao`, `aceita()`, `parse()`, `tipos_documentais()`
3. Registre em `core/parsers/registry.py`:
   ```python
   from .meu_contrato_parser import MeuContratoParser
   self.registrar(MeuContratoParser())
   ```
4. Adicione testes em `tests/test_parsers/test_meu_contrato_parser.py`

---

## Roadmap

> **Status ao vivo** dos marcos/blocks vive em `docs/ROADMAP.md` e em `cognitive_arch_V2` (STATE/NEXT/BLOCK_LOG). A tabela abaixo é visão de longo prazo, não status em tempo real.

| Marco | Descrição | Status |
|-------|-----------|--------|
| 0 | Estrutura e base do projeto | ✅ Concluído |
| 1 | Parser de código documental | ✅ Concluído |
| 2 | Importador da Lista de Documentos (Excel) | ✅ Concluído |
| 3 | Importador do ID/Índice | ✅ Concluído |
| 4 | Banco SQLite (estrutura base) | ✅ Concluído |
| 5 | Dashboard inicial | ✅ Concluído |
| 6 | Comparação ID × Lista | ✅ Concluído |
| 7 | Leitor de pasta SharePoint/local | ✅ Concluído |
| 8 | Cadastro manual | ✅ Concluído |
| 9 | Motor de status | ✅ Concluído |
| 10 | Exportação de relatórios | ✅ Concluído |
| 10.6 | Consolidação Arquitetural Pré-Produto | ✅ Concluído |
| 10.7 | Revisão do Cadastro Manual e Fluxo de Entrada | 🔄 Em andamento |
| 11 | Central de Pendências e Edição Operacional | 🔲 Pendente |
| 12 | Página de Edição e Correção de Documento | 🔲 Pendente |
| 13 | Conciliação Assistida | 🔲 Pendente |
| 14 | Página de GRDs | 🔲 Pendente |
| 15 | Importador de Status GED/PW | 🔲 Pendente |
| 16 | Relatório Executivo em PDF | 🔲 Pendente |
| 17 | Snapshots Mensais | 🔲 Pendente |
| 18 | Gestão de Contratos | 🔲 Pendente |
| 19 | Auditabilidade Completa | 🔲 Pendente |
| 20 | Preparação para Apresentação / Produto | 🔲 Pendente |

---

## Descrição dos Marcos Futuros

### Marco 10.7 — Revisão do Cadastro Manual e Fluxo de Entrada
Transformar o Cadastro Manual em um fluxo mais seguro, controlado e produtivo para lançamento de documentos técnicos. **Em andamento.**

**Decisão de produto:** fluxo principal é a lista de códigos colados e analisados via textarea (não formulário segmentado individual). O textarea aceita múltiplos códigos (um por linha) — o cadastro em lote já funciona naturalmente.

**Já entregue:** `validar_partes_codigo` em `codigo_builder.py`; `dados_derivados_codigo.py` (exibição somente leitura); `CadastroService.obter_dados_derivados_parseado`; dados derivados (tipo, trecho, disciplina, etapa, sequencial) readonly em cada card do Cadastro Manual; testes verificando fluxo principal.

**Sub-marcos concluídos:** 10.7.1 Documentação · 10.7.2 Experimentação segmentada (entrada por lista mantida) · 10.7.3 Dados derivados readonly nos cards.

**Pendente:** 10.7.4 Preview consolidado antes de salvar · 10.7.5 UX visual dos cards · 10.7.6 Testes e documentação final.

**Fora do escopo:** Central de Pendências, GRDs, PDF, Snapshots, Django, SQLAlchemy, nova autenticação, alteração de schema sem justificativa.

### Marco 11 — Central de Pendências e Edição Operacional
Página central onde o usuário vê tudo que exige ação e consegue tratar sem sair do app.

**Categorias de pendência:**
- Documentos previstos sem movimentação
- Documentos na Lista que não existem no ID
- Arquivos sem documento vinculado
- Documentos sem arquivo
- Códigos inválidos
- Revisões sem data
- Documentos sem objeto/título
- Divergências entre título do ID e título da Lista
- Documentos emitidos sem análise
- Documentos com análise atrasada

**Entregas:** página "Central de Pendências", agrupamento por categoria, filtros (tipo/disciplina/trecho/status/criticidade), botão abrir documento, botão marcar como resolvido, botão ignorar/aceitar divergência, link para edição, testes do motor de pendências.

### Marco 12 — Página de Edição e Correção de Documento
Permitir editar dados controlados sem precisar voltar ao Excel ou mexer direto no banco.

**Entregas:** tela de edição do documento; edição de título, disciplina, modalidade, estrutura, fase, responsável e observações; ativar/inativar documento; correção de dados importados; validação antes de salvar; log simples da alteração.

### Marco 13 — Conciliação Assistida
Transformar divergências ID × Lista em fluxo de decisão com ações concretas.

**Ações disponíveis por divergência:** manter dado do ID; manter dado da Lista; atualizar cadastro; marcar divergência como aceita; ignorar temporariamente; enviar para revisão posterior.

### Marco 14 — Página de GRDs
Área própria para Guia de Remessa/GRD com controle de vínculo.

**Entregas:** listar GRDs; buscar por número; filtrar por data/setor/status; ver documentos vinculados; identificar revisão sem GRD; identificar GRD sem documento; corrigir vínculo; exportar relatório de GRDs.

### Marco 15 — Importador de Status GED/PW
Importar manualmente relatórios do GED/ProjectWise sem API.

**Entregas:** importador CSV/XLSX de relatório GED; mapeamento de colunas; prévia antes de aplicar; atualização de situação, data de análise e retorno/comentário; relatório de divergências; rollback por lote (se viável).

### Marco 16 — Relatório Executivo em PDF
Gerar PDF de uma página para reunião de coordenação.

**Entregas:** resumo geral (avanço %, previstos, aprovados, em análise, pendentes); pendências críticas; avanço por disciplina e por trecho; data da última importação; exportação PDF.

### Marco 17 — Snapshots Mensais
Guardar histórico da evolução do contrato para análise de tendência.

**Entregas:** salvar snapshot mensal; comparar mês atual × mês anterior; evolução de aprovados, pendências e documentos emitidos; gráfico histórico.

### Marco 18 — Gestão de Contratos
Preparar o sistema para múltiplas obras e contratos.

**Entregas:** tela de contratos; criar/editar/ativar/desativar contrato; selecionar contrato ativo; duplicar configuração; filtrar dashboards por contrato; preparar parser/configuração por contrato.

### Marco 19 — Auditabilidade Completa
Registrar todas as mudanças relevantes para rastreabilidade.

**Entregas:** tabela de audit log; registrar edição manual, importação, resolução de pendência e alteração de status; mostrar histórico no detalhe do documento.

### Marco 20 — Preparação para Apresentação / Produto
Preparar o projeto para ser mostrado profissionalmente.

**Entregas:** README atualizado; changelog; prints das telas; instrução de instalação e uso; roteiro de apresentação; versão v0.1.0. *(Nota: o "modo demo" foi tentado e removido por decisão de produto — não faz parte deste marco.)*

---

## Importadores — ListaImporter (Marco 2)

`core/importers/lista_importer.py` — importa a aba "Lista de documentos" do Excel.

**Detalhes técnicos críticos:**
- A planilha tem **dois níveis de cabeçalho**: linha 1 = grupos (ALYA, METRÔ…), linha 2 = nomes reais.  
  Lemos com `header=1` (pandas) = Excel linha 2.
- Há **nomes de colunas duplicados** (GRD, DATA ENVIO, SITUAÇÃO, MEDIÇÃO, TOTAL CONTRATO…).  
  O acesso é **sempre por posição** (`iloc`), nunca por nome. As posições estão em `_COL` no módulo.
- Cada linha Excel = 1 revisão. O mesmo CÓDIGO aparece N vezes (Rev 1, Rev 2…).
- `ultima_revisao` é calculado ao final da importação (max revisão por documento).
- Reimportação é **idempotente** — upsert tanto em `documentos` quanto em `revisoes`.
- Erros por linha não abortam as demais — são gravados em `inconsistencias`.

```python
from core.importers.lista_importer import ListaImporter

importer = ListaImporter()                          # usa db/sclme.db
resultado = importer.importar("Lista Mestra.xlsx", contrato_id=1)
print(resultado.novos_documentos, resultado.novas_revisoes)
```

---

## Convenções

- **Sem comentários óbvios** — o código se documenta pelos nomes; comentários só para WHY não-óbvio
- **Sem mocks no banco** — testes de importação devem usar SQLite em arquivo temporário (`tmp_path`), nunca mocks
- **`get_connection()`** — toda conexão ao banco passa por aqui (garante `PRAGMA foreign_keys = ON`)
- **`ErroDeparse` é retorno, não exceção** — parsers nunca lançam exceção; erros são valores tipados
- **Commits em português** — mensagens de commit seguem o idioma do projeto
