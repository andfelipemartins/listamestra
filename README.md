# SCLME — Sistema de Controle de Lista Mestra de Projetos Executivos

Sistema local para controle documental de engenharia, desenvolvido como alternativa
escalável à planilha Excel atual.

**Primeiro caso de uso:** Linha 15 — Metrô de São Paulo.

---

## Stack

| Camada          | Tecnologia |
|-----------------|------------|
| Interface        | Streamlit  |
| Banco de dados   | SQLite     |
| Processamento    | Pandas     |
| Excel I/O        | OpenPyXL   |
| Visualização     | Plotly     |

---

## Estrutura de Pastas

```
sclme/
├── main.py                         # Home page — grade de contratos (ponto de entrada)
├── pages/                          # Páginas Streamlit (multi-page app)
│   ├── 1_Dashboard.py              # Dashboard de progresso por status e trecho
│   ├── 2_Importacao.py             # Upload de Excel + nomes.txt
│   ├── 3_Comparacao.py             # Comparação ID × Lista
│   ├── 4_CadastroManual.py         # Cadastro manual com builder de código
│   └── 5_Documento.py              # Detalhe por documento
├── app/
│   ├── session.py                  # Contrato ativo e helpers de sessão
│   └── components/                 # Widgets reutilizáveis (reservado)
├── core/
│   ├── parsers/
│   │   ├── base_parser.py          # Interface abstrata (BaseParser, CodigoParseado)
│   │   ├── linha15_parser.py       # Parser da Linha 15 — Metrô SP
│   │   ├── registry.py             # Registro e seleção automática de parsers
│   │   ├── arquivo_parser.py       # Parser de nome de arquivo (CODIGO-REV-VER.ext)
│   │   └── codigo_builder.py       # Montagem/desmontagem de código Linha 15
│   ├── importers/
│   │   ├── lista_importer.py       # Lista de Documentos → documentos + revisoes
│   │   ├── id_importer.py          # Índice de Documentos → documentos_previstos
│   │   └── arquivos_importer.py    # nomes.txt → arquivos vinculados
│   ├── engine/
│   │   ├── status.py               # Classificação de status, alertas, progresso
│   │   ├── comparacao.py           # Comparação ID × Lista (ResultadoComparacao)
│   │   ├── preview_arquivos.py     # Preview dry-run de importação de arquivos
│   │   ├── disciplinas.py          # Tabela A1–Z2 de estruturas/disciplinas
│   │   └── emissao_inicial.py      # Recalculo cronológico de EMISSÃO INICIAL
│   ├── exporters/
│   │   └── excel_exporter.py       # Geração de relatórios Excel (.xlsx)
│   └── auth/
│       └── permissions.py          # Perfis e permissões (can_perfil, can, require_permission)
├── db/
│   ├── connection.py               # Fábrica de conexões SQLite (FK + row_factory)
│   └── sclme.db                    # Banco gerado localmente (não versionado)
├── scripts/
│   └── init_db.py                  # Cria tabelas e migra colunas novas (idempotente)
├── tests/
│   ├── test_parsers/
│   ├── test_importers/
│   ├── test_engine/
│   ├── test_exporters/
│   └── test_auth/
├── requirements.txt
└── README.md
```

---

## Instalação

```bash
# 1. Crie o ambiente virtual
python -m venv .venv
.venv\Scripts\activate        # Windows

# 2. Instale as dependências
pip install -r requirements.txt

# 3. Inicialize o banco de dados
python scripts/init_db.py

# 4. Rode o app
streamlit run main.py
```

---

## Rodar os testes

```bash
pytest tests/ -v
# ou com cobertura:
pytest tests/ -v --cov=core --cov-report=term-missing
```

---

## Padrão de Código — Linha 15 (Metrô SP)

Formato: `TIPO-LINHA.TRECHO.SUBTRECHO.UNIDADE-ETAPACLS-SEQUENCIAL`

Exemplo: `DE-15.25.00.00-6A1-1001`

| Parte      | Valor | Significado       |
|------------|-------|-------------------|
| TIPO       | DE    | Desenho           |
| LINHA      | 15    | Linha 15          |
| TRECHO     | 25    | Trecho da obra    |
| SUBTRECHO  | 00    | Subtrecho         |
| UNIDADE    | 00    | Unidade           |
| ETAPA      | 6     | Etapa do contrato |
| CLASSE     | A     | Classe documental |
| SUBCLASSE  | 1     | Subclasse         |
| SEQUENCIAL | 1001  | Número sequencial |

---

## Roadmap

| Marco | Descrição                              | Status       |
|-------|----------------------------------------|--------------|
| 0     | Estrutura e base do projeto            | ✅ Concluído  |
| 1     | Parser de código documental            | ✅ Concluído  |
| 2     | Importador da Lista de Documentos      | ✅ Concluído  |
| 3     | Importador do ID/Índice                | ✅ Concluído  |
| 4     | Banco SQLite (estrutura base)          | ✅ Concluído  |
| 5     | Dashboard inicial                      | ✅ Concluído  |
| 6     | Comparação ID × Lista                  | ✅ Concluído  |
| 7     | Leitor de pasta SharePoint/local       | ✅ Concluído  |
| 8     | Cadastro manual                        | ✅ Concluído  |
| 9     | Motor de status                        | ✅ Concluído  |
| 10    | Exportação de relatórios               | ✅ Concluído  |
| 11    | Central de Pendências e Edição Operacional | 🔲 Pendente |
| 12    | Página de Edição e Correção de Documento   | 🔲 Pendente |
| 13    | Conciliação Assistida                  | 🔲 Pendente  |
| 14    | Página de GRDs                         | 🔲 Pendente  |
| 15    | Importador de Status GED/PW            | 🔲 Pendente  |
| 16    | Relatório Executivo em PDF             | 🔲 Pendente  |
| 17    | Snapshots Mensais                      | 🔲 Pendente  |
| 18    | Gestão de Contratos                    | 🔲 Pendente  |
| 19    | Auditabilidade Completa                | 🔲 Pendente  |
| 20    | Preparação para Apresentação / Produto | 🔲 Pendente  |
