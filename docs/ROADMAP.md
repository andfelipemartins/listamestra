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
| 10.7 | Revisao do Cadastro Manual e Fluxo de Entrada | Transformar o Cadastro Manual em fluxo seguro e controlado | Pendente |

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

O Cadastro Manual atual e fragil para uso operacional:

- o codigo documental e preenchido de forma livre, sem validacao segmentada;
- campos derivados do codigo (tipo, trecho, estrutura/disciplina, etapa, sequencial) sao digitados manualmente, gerando erros de consistencia;
- nao existe previa consolidada antes de salvar;
- nao e possivel cadastrar multiplos documentos em uma unica operacao;
- a interface permite que erros humanos passem sem bloqueio.

### Resultado Esperado

O Marco 10.7 devera entregar:

- componente de entrada segmentada do codigo documental;
- opcao de colar codigo completo e decompor automaticamente via parser existente;
- campos derivados do codigo (tipo, trecho, disciplina, etapa, sequencial) exibidos como somente leitura;
- preview consolidado dos dados antes de salvar;
- confirmacao explicita antes da persistencia;
- cadastro em lote (multiplos documentos em uma unica operacao);
- reaproveitamento do `CadastroService` existente;
- testes para entrada segmentada, preview e lote.

### Sub-marcos

| Sub-marco | Descricao |
| --- | --- |
| 10.7.1 | Documentar o Marco 10.7 |
| 10.7.2 | Criar componente de codigo segmentado |
| 10.7.3 | Travar campos derivados do codigo |
| 10.7.4 | Criar preview antes de salvar |
| 10.7.5 | Criar cadastro em lote |
| 10.7.6 | Ajustar UX visual do Cadastro Manual |
| 10.7.7 | Atualizar testes e documentacao |

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

