# SCLME — Sistema de Controle de Lista Mestra de Projetos Executivos

## O que é este projeto

Sistema local de controle documental de engenharia para a **Linha 15 — Metrô de São Paulo**.
Substitui uma planilha Excel manual por uma aplicação Streamlit + SQLite rastreável e auditável.

**Domínio:** Documentos técnicos de obras de metrô (Desenhos, Memoriais, Relatórios, Índices etc.).  
**Usuário principal:** Gestor de documentação / engenheiro responsável pelo controle da Lista Mestra.

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
├── main.py                     # Home page Streamlit (estado do sistema + links)
├── pages/                      # Páginas Streamlit (multi-page app — ao lado do main.py)
│   ├── 1_Dashboard.py          # Dashboard de progresso por status e trecho
│   ├── 2_Importacao.py         # Upload de Excel + criação de contrato
│   └── 3_Comparacao.py         # Comparação ID × Lista (ausentes, extras, divergências)
├── core/
│   ├── parsers/                # Interpretação de códigos documentais
│   │   ├── base_parser.py      # Contrato (BaseParser, CodigoParseado, ErroDeparse)
│   │   ├── linha15_parser.py   # Parser da Linha 15 — Metrô SP
│   │   └── registry.py         # Seleção automática de parser por contrato
│   ├── importers/              # Leitura de Excel
│   │   ├── lista_importer.py   # Lista de Documentos → documentos + revisoes
│   │   └── id_importer.py      # Índice de Documentos → documentos_previstos
│   ├── engine/                 # Regras de negócio
│   │   ├── status.py           # Classificação de status documental
│   │   └── comparacao.py       # Comparação ID × Lista (ResultadoComparacao)
│   └── exporters/              # Geração de relatórios (Marco 10+)
├── app/
│   └── components/             # Widgets reutilizáveis (futuro)
├── db/
│   ├── connection.py           # Fábrica de conexões SQLite (FK + row_factory)
│   └── sclme.db                # Banco gerado localmente (não versionado)
├── scripts/
│   └── init_db.py              # Cria todas as tabelas (idempotente)
└── tests/
    └── test_parsers/
        └── test_linha15_parser.py   # 49 testes — 100% passando
```

### Camadas e responsabilidades

| Camada | Responsabilidade |
|--------|-----------------|
| `core/parsers` | Interpretação e validação de códigos documentais |
| `core/importers` | Leitura de fontes externas (Excel) |
| `core/engine` | Regras de negócio (status, comparações, alertas) |
| `pages/` | Interface Streamlit — sem lógica de negócio; consome `core/` |
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
| CLASSE | A | 1 letra maiúscula (A–I) |
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
| `revisoes` | Histórico de revisões/versões de cada documento |
| `documentos_previstos` | Escopo previsto (vindo do Índice de Documentos) |
| `arquivos` | Arquivos físicos/digitais encontrados |
| `importacoes` | Rastreabilidade de cada lote importado |
| `inconsistencias` | Erros/alertas detectados durante importações |

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

| Marco | Descrição | Status |
|-------|-----------|--------|
| 0 | Estrutura e base do projeto | ✅ Concluído |
| 1 | Parser de código documental | ✅ Concluído |
| 2 | Importador da Lista de Documentos (Excel) | ✅ Concluído |
| 3 | Importador do ID/Índice | ✅ Concluído |
| 4 | Banco SQLite (estrutura base) | ✅ Concluído |
| 5 | Dashboard inicial | ✅ Concluído |
| 6 | Comparação ID × Lista | ✅ Concluído |
| 7 | Leitor de pasta SharePoint/local | 🔲 Pendente |
| 8 | Cadastro manual | 🔲 Pendente |
| 9 | Motor de status | 🔲 Pendente |
| 10 | Exportação de relatórios | 🔲 Pendente |

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
