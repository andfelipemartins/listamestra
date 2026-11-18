# Decisões de produto

Registro das decisões do dono do produto, na ordem em que foram tomadas. Cada uma cita
a pergunta do Control Room que a originou. Uma decisão só muda por outra decisão
registrada aqui, que a substitui.

---

## D-001 · Identidade: plataforma de gestão técnica e documental de engenharia

*Origem: A1 · 2026-11-18*

O SCLME deixa de ser um gerenciador documental preso às regras do Metrô e passa a ser
uma **plataforma de gestão técnica e documental para o dia a dia da engenharia**: engenheiros,
projetistas, auxiliares de engenharia e quem faz controle técnico e documental.

- Uma plataforma, vários contratos. Cada contrato tem seu próprio ambiente, com suas
  regras de codificação, disciplinas e critérios de organização. As ferramentas são
  compartilhadas e as particularidades de cada contrato são configuração.
- Exemplos reais que mostram a necessidade: o contrato de Gestão da Linha 15 (manuais e
  padrões já definidos) e o padrão de codificação da **SPObras**, que tem manual e
  estrutura diferentes dos do Metrô. São só exemplos. A plataforma não é feita para
  nenhum dos dois (ver D-005).
- O diferencial não é juntar muitas ferramentas, e sim deixar cada organização
  configurar o próprio ambiente e centralizar informação que hoje está espalhada em
  planilhas, pastas, e-mails e programas.
- Princípios: modular, leve e com um núcleo estável. Não reinventar ferramentas de
  áreas fora do domínio (por exemplo, o Comercial). Manter espaço para revisões de
  arquitetura e mudanças de direção.

## D-002 · Generalização: núcleo genérico com contrato configurável

*Origem: A2 · 2026-11-18*

O núcleo vira controle documental de engenharia. Formato de código, trechos,
disciplinas e vocabulário passam a ser **configuração de cada contrato**. Nenhum
contrato ou órgão fica fixo no código (ver D-005).

## D-003 · Destino em 12 meses: ferramenta da equipe/empresa

*Origem: A4 · 2026-11-18*

O produto deve servir à equipe e à empresa, não só ao dono. Isso exige multiusuário,
login real e deploy. Reabre a decisão de stack registrada nos ADRs 0001 e 0002
(Streamlit + SQLite hoje, Django + PostgreSQL como destino provável). A decisão de
stack em si ainda está pendente (pergunta G1).

## D-004 · Escopo ampliado (visão de longo prazo, sem compromisso de prazo)

*Origem: A1 e A3 · 2026-11-18*

Além da Lista Mestra, a plataforma deve cobrir, de forma progressiva:

- **Controle documental geral**, não só dos documentos codificados: ARTs, currículos
  de profissionais, contratos de empresas terceirizadas, documentação do contrato e da
  licitação.
- **Interfaces com outros setores** que seguem as mesmas premissas documentais do
  cliente: Qualidade, Planejamento, Fiscalização, Gestão de Contratos.
- **Contratos e medições de terceiros**: acompanhar entregáveis, revisões,
  aprovações e a liberação de medições, sem substituir sistemas financeiros ou
  comerciais.
- **Prazos, lembretes, datas e cronograma**, reduzindo a dependência de planilhas.
- **Ferramentas de produtividade**, como operações com PDF (unir, dividir,
  reorganizar, converter, extrair páginas), para não depender de serviços externos.
- **Base de conhecimento do contrato**: informação de e-mails, contexto da obra e
  acesso aos projetos (integração com SharePoint ou armazenamento próprio), com busca
  do tipo "preciso do projeto X".
- **IA integrada** no futuro, para leitura de documentos e automação de tarefas.

A ferramenta ajuda as pessoas e não as substitui: ela centraliza e organiza o trabalho.
A ordem de entrega desses módulos ainda não foi definida (pergunta D1).

## D-005 · Nada fixo para nenhum contrato: perfil de contrato configurável

*Origem: conversa com o dono · 2026-11-18*

A plataforma não é feita para a Linha 15, para a SPObras nem para nenhum outro órgão
ou obra. Ela traz as ferramentas, e cada contrato é descrito dentro dela:

- Existe uma área de **configuração do contrato** (perfil do contrato), usada por um
  administrador. Ali se descreve como é a documentação daquele contrato: a estrutura do
  código documental, o significado de cada parte, os valores válidos (tipos, trechos,
  disciplinas etc.) e o vocabulário.
- A partir dessa descrição, o sistema passa a interpretar, validar e organizar os
  documentos daquele contrato. O mesmo programa atende contratos com padrões diferentes.
- A configuração pode virar um **serviço**: o dono (ou outro especialista), com ajuda de
  IA, lê o manual do cliente, resume como o código funciona e entrega o perfil pronto.
- Linha 15 e SPObras servem como **casos de teste** da configuração: se os dois padrões
  couberem no mesmo modelo de perfil, o modelo é bom o suficiente.

## D-006 · Perfis de uso: quem entra na plataforma e o que vê

*Origem: B1 · 2026-11-18*

A plataforma serve aos dois lados do contrato, e não só ao escritório que gerencia:

- **Administrador do contrato**: responsável pela configuração. Altera a codificação
  documental do contrato e as demais personalizações permitidas (ver D-005).
- **Equipe técnica interna**: engenheiros das frentes, auxiliares técnicos e de
  engenharia. São os usuários do dia a dia.
- **Projetista contratado (externo)**: perfil próprio, simples e didático, que se aprende
  num treinamento rápido. Serve para subir os entregáveis e informar primeira emissão e
  revisões, evitando problemas de versão, revisão e medição (inclusive o que já foi medido
  e o que falta medir).
- **Chefia e coordenação do contrato**: pode usar as ferramentas, mas precisa no mínimo
  de dashboard e de **atribuição de tarefas** a pessoas (o que deve ser entregue, se está
  em andamento ou finalizado, e o prazo).
- **Visualização por link fixo, sem login**: uma tela de acompanhamento ("olho de Deus")
  com os números do contrato (total de projetos a elaborar, aprovados, em revisão,
  reprovados), a lista mestra e gráficos (pizza, progressão, histograma). O conteúdo
  exato ainda será definido.
- **Cliente/órgão** (ex.: Metrô): improvável que use, porque já tem sistema próprio. No
  máximo, visualização.

Requisito transversal: tudo auditável, com histórico gravado e contextual, num formato
que depois possa ser lido por outra ferramenta, como uma LLM.

Novo módulo citado: **gestão de tarefas da equipe** (atribuir, acompanhar status e prazo),
dentro da ideia de gerenciar a engenharia como um todo, incluindo as pessoas.

## D-007 · Stack: decidir antes da generalização

*Origem: G1 · 2026-11-18*

A decisão de stack (Streamlit + SQLite hoje, Django + PostgreSQL provável) será tomada
**antes** de generalizar o modelo de contrato, para que a generalização já nasça na stack
final. O Claude prepara um estudo curto em forma de ADR comparando as opções, e o dono
decide. Até lá, nada de generalização na stack atual nem migração para Django.

## D-008 · Codificação e lógica de revisão são configuração do contrato

*Origem: G2 · 2026-11-18*

Confirma e detalha D-005. Cada cliente tem seu manual ou IT de controle documental, e a
plataforma precisa de uma **seção de personalização** em que a informação dos documentos
contratuais é extraída e cadastrada, para o sistema entender como aquele contrato
funciona. Isso inclui não só a estrutura do código, mas também a **lógica de revisão**,
que muda de cliente para cliente (por exemplo, revisões alfabéticas A, B, C… que viram
número ao serem aprovadas, ou revisões numéricas que passam a combinar letra e número).
O dono considera esse ponto o cerne do produto.

Material de referência anexado pelo dono: IT-GPO-052/2012 (EMTU, padrão parecido com o do
Metrô), MAN-10-201 rev. 04 (Metrô) e o Manual de Padronização MP-SQ-SP-00-9R-001 L
(SPObras). Resumo do que foi extraído em `docs/contratos/casos-de-teste.md`.

Em aberto: o dono admite a hipótese de a configuração genérica se mostrar inviável. Nesse
caso, o produto seria adaptado para cada contrato, com apoio de código e IA, como serviço.
O Claude deve avaliar os limites das duas abordagens antes da generalização.

## D-009 · Nome: manter SCLME por enquanto

*Origem: G3 · 2026-11-18*

O nome SCLME continua. A troca fica para quando o produto for apresentado à empresa.

## D-010 · Prioridade de entrega: Lista Mestra primeiro

*Origem: D1 · 2026-11-18*

1. **Controle completo e definitivo da Lista Mestra**, substituindo a planilha com macro que
   ainda está em uso. Boa parte já funciona no Streamlit.
2. Em seguida, num mesmo pacote: **GRD** (já existe, precisa de melhorias), **Central de
   Pendências** e **dashboard por perfil** (D-006).

## D-011 · Primeiro Block da esteira: tela da Central de Pendências (block-011)

*Origem: D2 · 2026-11-18*

O dono não lembra mais o conteúdo de cada Marco. Toda pergunta e todo relatório que citar
um Marco ou Block deve trazer um resumo de uma linha do que ele entrega.

## D-012 · Autonomia da esteira

*Origem: E1 a E4 · 2026-11-18*

- **E1:** o Claude conduz um Marco inteiro sozinho, e o dono aprova no fim.
- **E2:** worktrees, branches e subagentes liberados, com regras (ver ESTEIRA.md).
- **E3:** o Codex roda como no Bastion, com o CLI `codex exec`, gpt-6-luna em xhigh.
- **E4:** commit automático por Block, depois de conferido pelo Claude. Push só com o dono.

## D-013 · Cognitive Arch: backup e hardening

*Origem: F1 e F2 · 2026-11-18*

- **F1:** a `cognitive_arch_V2/` ganha um repositório Git privado próprio, separado do
  repositório do produto. Já existe o repositório local. Criar o remoto no GitHub depende
  da autorização de push do dono.
- **F2:** os defeitos do SDK são corrigidos antes de a esteira rodar Marcos inteiros (block-012).

## D-014 · Telas atuais e Cadastro Manual

*Origem: C1 e C2 · 2026-11-18*

- O Marco 10.7 (UX do Cadastro Manual) será **refeito depois da nova visão**, e não fechado
  como estava.
- Problemas lembrados: login e perfis ruins, telas montadas sem fluxo. Falta definir qual é a
  primeira tela de cada perfil e para onde cada clique leva. Isso vira um estudo de navegação.
- B2: a rotina varia por função (a auxiliar começa pelo PW, e-mail e Teams). Integração com o
  Outlook (resumo dos e-mails ao abrir) fica como ideia futura. O produto deve funcionar sem
  depender de autorização de TI até estar pronto para ser apresentado.

## D-015 · Painel de acompanhamento com PIN único

*Origem: H1 · 2026-11-18*

O link fixo do painel de acompanhamento pede um **PIN numérico simples** (cerca de 4
dígitos), compartilhado com a chefia, e não um login por pessoa. Somente leitura.

## D-016 · Fluxo atual de entrega do projetista

*Origem: H2 · 2026-11-18*

- Procedimento previsto: pasta do SharePoint para entregas → subpasta com a data invertida
  (`2026-11-18`) → subpasta por disciplina (`G6 - Terraplenagem`) → DWG, PDF e complementares.
- Na prática, muitos projetistas (principalmente os mais antigos) mandam por e-mail, anexo
  ou link de transferência, e a equipe refaz o procedimento por eles.
- Depois vêm a análise interna e a análise crítica, que pode voltar ao projetista ou ser
  corrigida pela própria equipe (ex.: carimbo).
- O perfil do projetista precisa ser simples, e a equipe precisa poder **lançar em nome do
  projetista**, porque nem todos vão usar a ferramenta.
- Procedimentos anexados: PE-ENG-001 (Documentação Técnica) e PE-ENG-002 (Processo de
  emissão, controle e aprovação). Cada contrato terá o próprio procedimento.

## D-017 · Arquivos em etapas

*Origem: H3 · 2026-11-18*

O armazenamento de arquivos (G4) será entregue em etapas. A escolha da primeira etapa
depende do estudo `docs/estudos/G4-armazenamento-de-arquivos.md`.

## D-018 · Lógica de revisão do Metrô (caso de teste)

*Origem: H4 · 2026-11-18 · manual MAN-10-207 rev. 00 anexado*

- Emissão inicial: **Rev 1 Ver 1**, status EM ANÁLISE.
- Resultado da análise:
  - NÃO CONFORME ou INCONSISTENTE → nova versão da mesma revisão (Rev 1 Ver 2);
  - NÃO APROVADO → nova revisão (Rev 2 Ver 1);
  - APROVADO → **Rev 0 Ver 1**;
  - CANCELADO → fim de linha do código.
- Toda revisão pode ter versões sem limite (Ver 1, 2, 3…), inclusive a Rev 0.
- Se um documento aprovado precisar ser mexido, a Rev 0 vira **A1**, e o ciclo se repete com
  letra: A1, A2… → aprovado vira **A**. Depois B1, B2… → B, e assim por diante.
- Rótulo cronológico: a primeira emissão é "Emissão Inicial", e cada nova revisão ou versão
  seguinte é "Revisão 1", "Revisão 2"…, em ordem de data.
- Isso precisa caber no perfil de contrato configurável (D-008) como uma **máquina de
  estados de revisão** configurável, e não como código fixo.
