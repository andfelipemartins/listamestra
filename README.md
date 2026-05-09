# SCLME — Sistema de Controle de Lista Mestra de Projetos Executivos

Sistema local para controle documental de engenharia, desenvolvido como alternativa
escalável à planilha Excel atual.

**Primeiro caso de uso:** Linha 15 — Metrô de São Paulo.

---

## Stack

| Camada         | Tecnologia   |
|----------------|--------------|
| Interface       | Streamlit    |
| Banco de dados  | SQLite       |
| Processamento   | Pandas       |
| Excel I/O       | OpenPyXL     |
| Visualização    | Plotly       |

---

## Estrutura de Pastas

```
sclme/
├── app/                    # Interface Streamlit
│   ├── pages/              # Páginas do app (multi-page)
│   └── components/         # Componentes reutilizáveis
├── core/                   # Lógica de negócio
│   ├── parsers/
│   │   ├── base_parser.py      # Interface abstrata (BaseParser)
│   │   ├── linha15_parser.py   # Parser da Linha 15 — Metrô SP
│   │   └── registry.py         # Registro e seleção de parsers
│   ├── importers/          # Importadores (Excel, CSV, pasta)
│   ├── exporters/          # Exportadores (Excel, relatórios)
│   └── engine/             # Motor de status e regras
├── db/
│   └── sclme.db            # Banco SQLite (gerado por scripts/init_db.py)
├── config/                 # Configurações por contrato
├── tests/
│   └── test_parsers/
│       └── test_linha15_parser.py   # 47 testes — 100% passando
├── docs/                   # Documentação técnica
├── scripts/
│   └── init_db.py          # Inicializa o banco de dados
├── data/samples/           # Dados de exemplo para testes
├── main.py                 # Ponto de entrada do Streamlit
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
pytest tests/ -v --cov=core/parsers --cov-report=term-missing
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

| Marco | Descrição                         | Status       |
|-------|-----------------------------------|--------------|
| 0     | Estrutura e base do projeto       | ✅ Concluído  |
| 1     | Parser de código documental       | ✅ Concluído  |
| 2     | Importador da Lista de Documentos | 🔲 Pendente   |
| 3     | Importador do ID/Índice           | 🔲 Pendente   |
| 4     | Banco SQLite (estrutura base)     | ✅ Concluído  |
| 5     | Dashboard inicial                 | 🔲 Pendente   |
| 6     | Comparação ID x Lista             | 🔲 Pendente   |
| 7     | Leitor de pasta SharePoint/local  | 🔲 Pendente   |
| 8     | Cadastro manual                   | 🔲 Pendente   |
| 9     | Motor de status                   | 🔲 Pendente   |
| 10    | Exportação de relatórios          | 🔲 Pendente   |
