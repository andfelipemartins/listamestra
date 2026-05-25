# Roadmap do SCLME

Data: 2026-05-16

## Objetivo

Este roadmap registra a sequencia de marcos do SCLME e explicita a insercao do Marco 10.6 antes da retomada de novas funcionalidades.

## Marcos Concluidos e Em Consolidacao

| Marco | Nome | Objetivo | Status |
| --- | --- | --- | --- |
| 0 | Estrutura e base do projeto | Criar base do projeto, organizacao inicial e ambiente | Concluido |
| 1 | Parser de codigo documental | Interpretar codigos documentais da Linha 15 | Concluido |
| 2 | Importador da Lista de Documentos | Importar documentos e revisoes da Lista | Concluido |
| 3 | Importador do ID/Indice | Importar documentos previstos | Concluido |
| 4 | Banco SQLite | Estrutura base de persistencia | Concluido |
| 5 | Dashboard inicial | Exibir indicadores principais | Concluido |
| 6 | Comparacao ID x Lista | Identificar ausentes, extras e divergencias | Concluido |
| 7 | Leitor de arquivos | Ler nomes de arquivos locais/SharePoint | Concluido |
| 8 | Cadastro manual | Permitir cadastro manual de documentos e revisoes | Concluido |
| 9 | Motor de status | Calcular status, alertas e aprovacao historica | Concluido |
| 10 | Exportacao de relatorios | Gerar arquivos Excel de apoio | Concluido |
| 10.6 | Consolidacao Arquitetural Pre-Produto | Reduzir acoplamento e preparar crescimento | Concluido |
| 10.7 | Revisao do Cadastro Manual e Fluxo de Entrada | Transformar o Cadastro Manual em fluxo seguro e controlado | Em andamento |

## Marco 10.6 - Consolidacao Arquitetural Pre-Produto

### Objetivo

Documentar e preparar a arquitetura para crescimento sem migrar imediatamente para Django.

### Motivacao

O MVP ja prova valor operacional, mas a analise arquitetural identificou riscos:

- SQL direto em paginas;
- paginas acumulando responsabilidades;
- dependencia forte de Streamlit;
- dependencia de SQLite dentro de `core`;
- ausencia de services/repositories;
- riscos para multiusuario, autenticacao e deploy corporativo.

### Resultado Entregue

O Marco 10.6 entregou:

- documentacao de arquitetura atual (`docs/ARCHITECTURE.md`);
- visao de produto (`docs/PRODUCT_VISION.md`);
- ADRs sobre stack atual, Django futuro e services/repositories (`docs/adr/`);
- camada completa de repositories implementada e testada:
  - `ContractRepository`;
  - `ImportacaoRepository`;
  - `DocumentoRepository`;
  - `RevisaoRepository`;
- camada completa de services implementada e testada:
  - `ContractService`;
  - `ImportacaoService`;
  - `DocumentoService`;
  - `CadastroService`;
  - `DashboardService`;
- paginas `1_Dashboard.py`, `4_CadastroManual.py` e `5_Documento.py` refatoradas para consumir exclusivamente as novas camadas;
- suite de testes com 570 testes passando.

## Marco 10.7 - Revisao do Cadastro Manual e Fluxo de Entrada

### Objetivo

Transformar o Cadastro Manual em um fluxo mais seguro, controlado e produtivo para lancamento de documentos tecnicos.

### Motivacao

O Cadastro Manual precisava de:

- validacao mais clara do codigo documental antes de salvar;
- exibicao somente leitura dos dados derivados do codigo (tipo, trecho, disciplina, etapa, sequencial);
- previa consolidada antes de persistir;
- suporte natural a multiplos documentos por operacao;
- reducao de erro humano sem complicar a interface.

### Decisao de Produto — Entrada por Lista

O Marco 10.7 definiu que o fluxo de entrada principal e a **lista de codigos colados e analisados via textarea**, nao um formulario segmentado campo a campo. Essa decisao foi tomada apos experimentacao:

- formulario segmentado individual foi implementado e testado;
- a abordagem aumentou complexidade de UI sem ganho operacional claro;
- o modelo de colar multiplos codigos (um por linha) e mais rapido para o uso real;
- o cadastro em lote ja funciona naturalmente pelo textarea.

### Resultado Entregue

Concluido no marco:

- `lógica pura validar_partes_codigo` em `core/parsers/codigo_builder.py`;
- componente `app/components/dados_derivados_codigo.py` para exibicao somente leitura;
- metodo `CadastroService.obter_dados_derivados_parseado` para extrair campos derivados do parse;
- dados derivados (tipo, linha, trecho, nome do trecho, subtrecho, unidade, etapa, classe/subclasse, disciplina/estrutura, sequencial) exibidos readonly em cada card do Cadastro Manual;
- textarea como fluxo principal de entrada de codigos (aceita um ou varios);
- testes atualizados verificando que o fluxo principal e o textarea e que o fluxo segmentado individual nao existe.

### Pendente

| Sub-marco | Descricao | Status |
| --- | --- | --- |
| 10.7.1 | Documentar o Marco 10.7 | Concluido |
| 10.7.2 | Entrada segmentada (experimentacao, decisao: textarea e o fluxo) | Concluido |
| 10.7.3 | Exibir dados derivados como somente leitura nos cards | Concluido |
| 10.7.4 | Preview consolidado antes de salvar | Concluido |
| 10.7.5 | UX visual — revisao dos cards e do fluxo de cadastro | Pendente |
| 10.7.6 | Atualizar testes e documentacao final | Pendente |

### Proximo Passo

O proximo sub-marco e o **10.7.5 — UX visual — revisao dos cards e do fluxo de cadastro**.

### Fora do Escopo

- Central de Pendencias;
- GRDs;
- PDF;
- Snapshots mensais;
- Django ou SQLAlchemy;
- Nova autenticacao;
- Alteracao de schema, salvo se estritamente necessario e justificado.

## Marcos Apos o 10.7

Com a revisao do fluxo de entrada concluida, o roadmap funcional de novas funcionalidades pode avancar:

| Marco | Nome | Objetivo |
| --- | --- | --- |
| 11 | Central de Pendencias | Consolidar pendencias operacionais e orientar acao do usuario |
| 12 | Edicao Operacional | Permitir correcao controlada de dados de documentos |
| 13 | Conciliacao Assistida | Transformar divergencias ID x Lista em fluxo de decisao |
| 14 | GRDs | Criar area propria para consulta e controle de GRDs |
| 15 | Importador de Status GED/PW | Importar relatorios externos de status e atualizar acompanhamento |

## Pendencias Arquiteturais Remanescentes

Os itens abaixo nao foram bloqueantes para o Marco 10.6 e podem ser tratados incrementalmente:

- `ArquivosService`;
- separacao de `core/auth` puro e `app/auth` UI;
- remocao gradual de `sys.path.insert`.

