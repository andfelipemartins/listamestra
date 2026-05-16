# Arquitetura do SCLME

Checkpoint arquitetural em 2026-05-16.

## Objetivo

O SCLME e um sistema Python/Streamlit/SQLite para controle documental de engenharia. A aplicacao substitui controles manuais em Excel por uma base rastreavel com importadores, parsers, dashboard, comparacao ID x Lista, cadastro manual, consulta de documentos, exportadores e testes automatizados.

Este documento registra a arquitetura atual sem propor migracao imediata de stack. A diretriz e consolidar o produto atual e preservar a possibilidade de evolucao futura.

## Stack Atual

| Camada | Tecnologia | Papel |
| --- | --- | --- |
| Interface | Streamlit | WebApp interno, formularios, dashboards, tabelas e navegacao |
| Banco local | SQLite | Persistencia simples, arquivo unico, facil de portar e inicializar |
| Processamento | Pandas | Leitura, normalizacao e transformacao tabular |
| Excel I/O | OpenPyXL | Leitura e escrita de arquivos `.xlsx` |
| Graficos | Plotly | Visualizacoes interativas no dashboard |
| Testes | Pytest | Testes de parsers, importadores, engine, exportadores e helpers |

## Estrutura de Camadas

```text
main.py             Entrada do app e navegacao
pages/              Paginas Streamlit
app/                Estado de sessao, contexto e componentes de interface
core/parsers/       Parsers de codigos documentais e nomes de arquivo
core/importers/     Importacao de Excel, ID e arquivos
core/engine/        Regras de negocio e calculos
core/exporters/     Exportacao de relatorios
core/auth/          Perfis e permissoes
db/                 Conexao SQLite e banco local
scripts/            Inicializacao e migracoes simples
tests/              Testes automatizados
docs/               Documentacao tecnica e de produto
```

## Responsabilidades

### `pages/`

As paginas Streamlit devem capturar input, chamar funcoes de servico e renderizar output. Elas podem organizar layout, mensagens, filtros e componentes visuais, mas nao devem concentrar regra de negocio.

### `core/`

O `core/` deve ser independente da interface. Regras de parsing, importacao, status, comparacao, progresso, alertas, exportacao e validacao devem viver aqui sempre que forem reutilizaveis ou testaveis.

### `db/`

O banco deve ser acessado por camada propria. A referencia atual e `db/connection.py`, que centraliza conexoes SQLite, `row_factory` e configuracoes como foreign keys. Paginas e modulos devem evitar `sqlite3.connect()` direto fora dessa camada.

### `app/`

O `app/` concentra estado de sessao, contexto lateral, perfil atual e helpers de interface. Ele pode depender de Streamlit. O `core/` nao deve depender de `app/`.

### `tests/`

Os testes devem priorizar `core/`, porque e ali que vivem as regras que nao podem variar com UI. Testes de pagina podem existir para helpers e transformacoes testaveis, mas o objetivo principal e proteger regras de negocio.

## Fluxos Principais

### Importacao da Lista de Documentos

1. Usuario faz upload da Lista de Documentos.
2. `pages/2_Importacao.py` captura o arquivo.
3. `core/importers/lista_importer.py` le a planilha.
4. O importer normaliza linhas, documentos e revisoes.
5. O banco registra `documentos`, `revisoes`, `importacoes` e `inconsistencias`.
6. Regras complementares recalculam emissao inicial e ultima revisao.

### Importacao do ID

1. Usuario faz upload do Indice de Documentos.
2. `core/importers/id_importer.py` identifica a aba ID e documentos previstos.
3. Cada documento previsto e gravado em `documentos_previstos`.
4. A comparacao ID x Lista passa a usar esse escopo previsto.

### Dashboard e Status

1. Dashboard chama `core/engine/status.py`.
2. `carregar_progresso()` retorna status atual e aprovacao historica.
3. Status atual reflete a ultima revisao.
4. Aprovacao historica considera revisoes finais por `label_revisao`, como `0` e letras puras (`A`, `B`, `C`...), sem contar intermediarias (`A1`, `B1`...).

### Comparacao ID x Lista

1. `core/engine/comparacao.py` cruza previstos e documentos importados.
2. Resultado classifica ausentes, extras e divergencias.
3. A pagina apenas exibe o resultado e oferece exportacao.

### Pesquisa de Documento

1. A pagina de pesquisa lista documentos do contrato ativo.
2. Busca normaliza acentos e caixa.
3. O detalhe mostra ficha, linha do tempo, arquivos e GRDs vinculados.

## Diretrizes Arquiteturais

- Regras de negocio devem ficar fora das paginas Streamlit.
- Paginas devem capturar input, chamar servicos e exibir output.
- `core/` deve ser independente da interface.
- Banco deve ser acessado por camada propria.
- Testes devem cobrir `core/` prioritariamente.
- Importadores devem ser idempotentes quando possivel.
- Erros por linha devem ser rastreaveis e nao devem abortar lotes inteiros sem necessidade.
- Dados derivados devem ser recalculaveis a partir das fontes importadas sempre que possivel.
- Exportacoes devem consumir os mesmos resultados usados pela UI, evitando divergencia entre tela e relatorio.

## Limitacoes Conhecidas

### Multiusuario

Streamlit com SQLite local atende bem a uso individual, demo e piloto simples. Para varios usuarios simultaneos gravando dados, o modelo precisa ser revisto.

### Autenticacao

O app possui perfis e permissoes internos, mas nao integra autenticacao corporativa. Nao ha login real com provedor externo, SSO, LDAP, Azure AD ou equivalente.

### Permissoes

As permissoes atuais ajudam a controlar visibilidade e acoes dentro do app, mas ainda nao devem ser tratadas como seguranca corporativa forte.

### Concorrencia

SQLite e adequado para baixo volume e operacao local. Gravacoes simultaneas, importacoes concorrentes e edicoes paralelas exigem cuidado adicional.

### Deploy Corporativo

Streamlit Community Cloud e util para demo, mas nao e arquitetura corporativa definitiva. Deploy interno pode exigir rede, autenticacao, banco gerenciado, backup, observabilidade e suporte de TI.

### CRUD Complexo

Streamlit permite formularios e edicoes simples, mas fluxos CRUD complexos, com auditoria detalhada, revisao, permissao fina e estados intermediarios, podem se tornar dificeis de manter apenas em paginas Streamlit.

## Caminhos de Evolucao

### Django + PostgreSQL

Boa opcao se o produto virar sistema interno robusto com usuarios, permissoes, CRUD, modelos relacionais, admin, auditoria e banco centralizado.

### Django + HTMX

Alternativa para manter backend forte em Python e construir uma interface web dinamica sem um frontend pesado. Pode ser adequada para telas operacionais, formularios e consultas.

### FastAPI + React/Next

Boa opcao para separacao clara entre API e frontend. Traz flexibilidade e melhor experiencia de produto, mas aumenta custo de desenvolvimento, deploy e manutencao.

### Power Platform

Pode atuar como camada complementar para formularios, aprovacao, automacoes com Outlook/SharePoint/Power Automate e integracao com ambiente corporativo Microsoft. Nao substitui necessariamente o motor de regras do SCLME.

## Decisao Atual

Manter a stack atual para consolidar a versao piloto. O objetivo imediato e confiabilidade das regras e clareza operacional, nao migracao tecnologica.

