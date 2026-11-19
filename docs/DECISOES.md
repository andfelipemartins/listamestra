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

## D-019 · Backup remoto da Cognitive Arch

*Origem: I1 · 2026-11-18*

A memória da esteira (`cognitive_arch_V2/`) tem um repositório privado próprio no GitHub
(`sclme-cognitive-arch`), com push automático a cada fechamento de Block. O código do produto
continua com push só pelo dono (D-012).

## D-020 · Stack: Django + PostgreSQL + HTMX, migração por etapas

*Origem: I3 · 2026-11-18 · aprova a ADR 0005*

A plataforma da equipe passa a ser construída em Django + PostgreSQL + HTMX, no diretório
`plataforma/`. O Streamlit continua funcionando até a paridade. As regras puras de `core/`
(motores de status, pendências e perfil de contrato) são reaproveitadas. O próximo Marco é a
**Fundação Django**. A Lista Mestra definitiva e o perfil configurável já nascem nela.

## D-021 · Marco 11 aprovado com ajustes; papel da Central de Pendências

*Origem: J1 · 2026-11-18*

- Ajuste pedido: o filtro por tipo "não faz nada". A causa era que os cards de resumo ignoravam
  os filtros e a lista ficava em seções fechadas. A correção é o block-013.
- Esclarecimento: a Central de Pendências **não é** o painel "olho de Deus" (esse é o painel de
  acompanhamento com PIN, D-015). Ela é o **controle de consistência interno** de quem opera a
  ferramenta: o motor automático detecta sozinho o que está faltando ou divergente, e o ideal é
  zero. O dono espera que a plataforma recalcule tudo assim que um dado entra, como o botão
  "atualizar" do macro, só que automático.

## D-022 · A planilha com macro é referência, não modelo

*Origem: I2 · 2026-11-18 · planilha em `entrada/`, módulos .bas anexados*

A planilha `Lista Mestra de Projetos Executivos - Macro.xlsm` mostra o tipo de informação
documental (colunas e abas) que o dono quer, mas **não deve ser copiada**. Ela tem gambiarras
que a plataforma precisa eliminar. Exemplo: é preciso deixar uma linha de revisão "prevista"
para um documento reprovado antes de a revisão chegar, só para o macro funcionar. Na
plataforma, a próxima revisão esperada é deduzida pelo ciclo de análise do perfil, sem linha
fictícia.

## D-023 · Correspondência de códigos entre perfis (Metrô × SPObras)

*Origem: I4 · 2026-11-18 · tabela de equivalência colada pelo dono*

O mesmo documento pode ter um código em cada padrão. Exemplo:
`DE-15.25.00.00-6B7-1501` (Metrô, sem revisão no código; a emissão inicial é Rev 1) equivale a
`DE-CC-EE-WW-5E-001-A` (SPObras, com a revisão A no código).

A tabela mostra que a correspondência **não sai de uma fórmula**:
- a classe/subclasse do Metrô vira outra classe na SPObras (B7 e P7 → E, C1 → T, D1 e D2 → I,
  F6 → S, G6 → Q, J1 a J3 → C, N3 → L…);
- o sequencial é renumerado por classe da SPObras (D2-1501 vira I-021);
- alguns tipos mudam (TC → CC).

> **Revista pela D-024.** A conclusão original era guardar a correspondência como dado (um
> documento com códigos de mais de um perfil). O dono recusou: a tabela serviu só para estudo.

## D-024 · O perfil são "caixas" com nome; nada de correspondência entre órgãos

*Origem: K1 · 2026-11-18*

- Analogia do dono: o código é uma fila de **caixas** (lacunas). No início do contrato, o admin
  diz quantas caixas existem, o que é cada uma (tipo, local, classe, sequencial, **revisão**…) e os
  valores válidos. O motor (quem carrega as caixas) é sempre o mesmo e funciona para qualquer
  conteúdo e qualquer número de caixas. Quando sobe uma revisão, o motor sabe pela configuração
  qual caixa mudar e como (regra do manual daquele contrato).
- **Não guardar correspondência de códigos entre órgãos/perfis.** Metrô × SPObras foi material
  de aprendizado para desenhar o motor, e não é um recurso.
- Caso real que motivou a tabela: no contrato com o Metrô, os projetos vão para a SPObras
  executar. O Metrô quer o nome do `.dwg` no código Metrô (para o PW), e o PDF sai com o
  carimbo e o código da SPObras. Por enquanto isso fica fora da plataforma.
- Consequência: o modelo `CodigoDocumento` com vários códigos por documento (block-015) é
  simplificado para um código por documento no perfil do contrato.

## D-025 · Resultado da análise vem do relatório exportado do PW

*Origem: K2 · 2026-11-18 · extração em `entrada/data.xlsx` (fora do Git)*

O resultado da análise do cliente é importado do relatório exportado do ProjectWise, com
prévia antes de gravar. Isso adianta o Marco 15. A extração tem 19 colunas, entre elas as
partes do código separadas, revisão, versão, `Current State Name`, datas de emissão e resposta, título,
nome do arquivo e o **Histórico do Workflow** (todas as passagens com data, como
`(1.1) Em Análise`), com o qual dá para remontar a linha do tempo inteira. Estados vistos:
Em Desenvolvimento, Em Análise, Para Aprovação, Em coleta de Assinaturas, Aprovado, Não
Aprovado, Não Conforme, Inconsistente, Erro de Assinatura, Cancelado, Revisão Superada.

## D-026 · Painel da chefia: começar pelo status, com o vocabulário do PW

*Origem: K3 · 2026-11-18*

- Primeira versão: o escopo (o que precisa ser emitido, ou seja, o ID) contrastado com quantos
  foram emitidos, quantos estão em análise, não aprovados e aprovados. Gráfico de pizza e de
  barras de progressão.
- Usar **os nomes do PW/Metrô** ("Não Aprovado", e não "Reprovado"), porque é o padrão que o
  mercado já conhece.
- Histograma × cronograma (onde deveríamos estar e onde estamos, pelas datas previstas no ID):
  fica para depois, com exemplos reais do dono. Ir passo a passo.

## D-027 · Status principais da plataforma: a plataforma simplifica o PW, não copia

*Origem: L1 · 2026-11-18*

- A extração do PW é fonte de dado, e não um modelo a copiar. Os status que importam são
  **A EMITIR** (está no ID e não foi emitido), **EM ANÁLISE**, **APROVADO** e **NÃO APROVADO**,
  além de CANCELADO como fim de linha.
- "Para Aprovação" e "Em coleta de Assinaturas" são trâmites internos do sistema do cliente. Para
  o dono, o documento já está praticamente aprovado: na prática, isso autoriza levar a revisão
  a campo enquanto corre o trâmite da revisão original (Rev 0). Esses estados contam como
  **APROVADO**.
- INCONSISTENTE e NÃO CONFORME existem porque o Metrô tem uma caixa **versão**: o documento nem
  chega a ser avaliado e volta como nova versão da mesma revisão. Em geral, o NÃO CONFORME se
  aplica a revisões originais, e o INCONSISTENTE a qualquer revisão, principalmente às iniciais.
  Esses status só existem num perfil que tenha a caixa versão.
- O agrupamento (estado do cliente → status da plataforma) é **configuração do perfil de
  contrato**, e não código.

## D-028 · Perfil de contrato = soma dos manuais do órgão, montada com ajuda da IA

*Origem: L2 · 2026-11-18 · MAN-10-202 rev. 09 anexado (em `entrada/referencias/`)*

- O Metrô tem manuais separados para obras civis (MAN-10-201) e para sistemas (MAN-10-202). Outros
  órgãos podem juntar ou separar de outro jeito. O perfil de um contrato é a **união** das tabelas
  dos manuais que valem para ele.
- O que importa é o nome de cada caixa e o significado de cada valor. Exemplo: na caixa
  "classe" do Metrô, o valor `P7` significa Iluminação (Tabela 4 do MAN-10-202). No Metrô, o rótulo
  é da combinação classe + subclasse, e não das partes separadas.
- Caminho desejado: o admin envia os PDFs dos manuais, a IA lê e propõe a configuração (caixas,
  valores e rótulos, ciclo de revisão), e o admin revisa e aprova. Essa proposta vira o perfil do
  contrato.

## D-029 · Importador do PW: formato fixo e data da última extração

*Origem: L3 e L4 · 2026-11-18*

- A extração do PW é tirada sempre que for alimentar o painel. O mapeamento é fixo neste formato
  de exportação, com aviso se uma coluna sumir, e o painel mostra a data da última extração.
- L4: os códigos reais (sem títulos, datas ou arquivos) podem ser versionados como fixture de
  teste.

## D-030 · Próximo Marco: dados reais + painel da chefia; INCONSISTENTE como grupo

*Origem: M1, M3 · 2026-11-18*

- Depois da Fundação Django, o próximo Marco importa o ID e a extração do PW da Linha 15 e monta
  o painel da chefia.
- Grupos do painel no perfil Metrô: A EMITIR, EM ANÁLISE, APROVADO, NÃO APROVADO e
  **INCONSISTENTE**. O grupo INCONSISTENTE junta Inconsistente e Não Conforme, porque a definição
  de inconsistente já é bem estabelecida na gestão da Linha 15. A regra continua sendo do perfil.

## D-031 · O ID vem do Excel de atributos do PW, e um contrato tem vários IDs

*Origem: M2 · 2026-11-18 · três IDs em `entrada/` (fora do Git)*

- Os três IDs (`ID-15.25.00.00-6A9-1001`, `-1002` e `-1501`) têm o mesmo formato: na aba
  `Planilha1`, as partes do código em colunas separadas, o título, o código completo (`Name`), o
  número do contrato e a marca `[Excluído]`. Eles somam **981 documentos previstos**.
- Um contrato tem **vários IDs**, cada um com seu escopo (civil, sistemas, SPTrans…). O previsto
  é a união dos IDs vigentes.
- O ID `-1501` renumerou o sequencial para a faixa 2000 (por exemplo, `ID-15.25.00.00-6A9-2001`)
  por ordem do cliente.
- Cruzamento com a extração do PW: 658 previstos já estão no PW, **323 ainda não foram emitidos**
  e **44 estão no PW sem constar em nenhum dos três IDs**.
- As abas auxiliares têm nomes de profissionais e empresas, ou seja, dados pessoais: não
  importar nem copiar.

## D-032 · O previsto vem de IDs parciais e da extração do ID atual do PW

*Origem: N1, N2 · 2026-11-18 · `entrada/ID PW.xlsx` (fora do Git)*

- É comum emitir **IDs parciais**: surgem documentos novos, é feito um ID parcial, ele é aprovado
  por e-mail e sobe para o PW. Por isso, o Excel do ID nem sempre está atualizado. Há também uma
  **extração do ID atual** dentro do PW, com tudo o que o cliente já registrou.
- A plataforma aceita as duas fontes: o Excel de atributos do ID e a extração do ID do PW. O
  previsto é a união das fontes vigentes. Um documento que está no PW e fora de qualquer ID vira
  pendência (ID desatualizado), e não erro.
- A extração do ID do PW tem 821 documentos, contra 693 do PW de situação. Só 9 documentos com
  situação ficam fora dela. Ela traz colunas de assinadores (nomes de pessoas), que **não são
  importadas**.
- Os 16 arquivos 15xx do PW são **RTs de ATO (classe A9)**, documentos reais emitidos há tempo e
  que deveriam constar no ID. Eles não têm relação com a renumeração 1500 → 2000, que foi outra
  decisão do cliente.
- Uma ferramenta futura para montar ID parcial dentro da plataforma fica registrada como ideia.

## D-033 · IA na plataforma: conversa aberta; servidor local quase descartado

*Origem: N3, N4 · 2026-11-18*

- O dono quer conversar antes de decidir e tende à opção B (modelo forte pela nuvem que a empresa
  aceitar). Ele ainda vai verificar se a empresa tem contrato de nuvem ou só o Copilot.
- Servidor local: quase descartado. A estrutura é grande (hardware, refrigeração) e só se
  justificaria com um ganho muito alto. A máquina do dono (RTX 4060 Ti com 8 GB de VRAM e 32 GB de
  RAM) não serve como teste representativo.
- Visão do dono: o assistente **não** pode ser um "chatbot de banco" limitado. No futuro, precisa
  ser algo mais elaborado. As funções listadas no estudo pareceram fracas.
- Enquanto a decisão não sai, o produto segue sem IA embutida, com o fluxo de fora (Claude Code →
  YAML → admin).

## D-034 · Painel da chefia: cancelado fora, filtros como tabela dinâmica, A7 aceita

*Origem: O1, P1, P2, P3, P5, P6 · 2026-11-18 (registrado pela checagem agendada das 12:56Z)*

- **O1:** o Marco Fundação Django foi aprovado sem ajustes.
- **P2:** cancelado é "pré-histórico": não entra na pizza, nos gráficos nem no avanço, do mesmo
  jeito que o dono tira os cancelados na tabela dinâmica do Excel. Inconsistente e Não Conforme
  continuam contando, porque exigem ação. A pizza mostra o total de documentos dividido em
  A EMITIR, APROVADO, EM ANÁLISE etc., e as barras mostram o mesmo por recorte (trecho, por
  exemplo). Sem filtro, aparece a visão geral do contrato para a reunião e para a gerência.
- O dono deixou em aberto como o "procedimento específico" (aprovação em até três revisões, meta
  de 80%) apareceria no painel: por documento, por disciplina? Ele pediu uma proposta.
- **P3:** o painel precisa de todo tipo de filtro, como uma tabela dinâmica do Excel: trecho, tipo
  (só DEs, MCs, RTs…), classe e o contrato inteiro sem filtro. Alguns recortes podem vir prontos,
  mas sem limitar o usuário.
- **P1:** 'Erro de Assinatura' e 'Em Desenvolvimento' saem de EM ANÁLISE e passam a ser **erro**.
  Erro de assinatura exige refazer, trocar o arquivo ou pedir que o cliente corrija. Em
  Desenvolvimento costuma ser emissão esquecida ou arquivo errado deixado no PW, que não pode ser
  apagado. Se veio na extração, o painel acusa, e a pessoa pondera: ignora, corrige ou pede a
  correção. O dono perguntou se isso fica simples. Proposta do Claude: os dois entram no grupo
  INCONSISTENTE, que já é o grupo do "precisa arrumar" (ver pergunta Q2).
- **P5:** no perfil SPObras, 'ALTERNATIVA NÃO ADOTADA' vai para o grupo CANCELADO.
- **P6:** a classe A7 existe, mesmo fora do MAN-10-201. Provavelmente é de qualidade (relatório
  mensal de qualidade). A responsável na empresa é da área de qualidade, e no Metrô também. O dono
  vai verificar se há um MAN específico. Enquanto isso, a A7 deve ser incorporada, porque a
  plataforma atende todos os setores da engenharia, qualidade incluída.

## D-035 · IA na plataforma: um chat dentro do gerenciador, com o contexto dos contratos

*Origem: M4, P4 · 2026-11-18 · complementa a D-033*

- **M4:** o dono não sabe ainda se a IA rodaria online ou offline. Ele cogitou um modelo menor
  num servidor do escritório, mas pediu para discutirmos as formas de integrar um LLM ao sistema.
  Na empresa, a ferramenta imposta é o Copilot, que ele avalia mal.
- **P4:** o que ele quer é um **chat dentro do gerenciador**, com a força do melhor modelo que a
  empresa tiver, onde ele possa jogar um PDF, perguntar por um documento ou pelo que diz um
  contrato, e que leia os projetos plotados do AutoCAD em PDF. O chat deve estar ligado às pastas
  do SharePoint e às informações do sistema, sem inventar coisas fora dele.
- Pergunta do dono que precisa de resposta: é possível ter essa força num chat fechado no sistema?
- Continua valendo a D-033: sem IA embutida até a conversa acontecer.

## D-036 · Erro de PW é um grupo próprio no painel, separado de INCONSISTENTE

*Origem: Q2 · 2026-11-18 (respondida às 23:06Z; registrado pela checagem agendada das 23:56Z) · substitui a proposta do Claude na D-034 (P1)*

- O dono recusou juntar tudo em INCONSISTENTE: ele precisa distinguir o que é inconsistência do
  que é erro.
- **INCONSISTENTE** é conceito de projeto: o projetista fez o documento fora do manual e das
  premissas do Metrô. Tem informação técnica, mas não segue o que o cliente pediu.
- **NÃO CONFORME**, pelo que o dono lembra, só apareceu até hoje em revisões originais (de
  aprovação), quando o cliente percebe algo que não tinha visto antes. A causa e o efeito acabam
  sendo os mesmos da inconsistência: a revisão se mantém e a versão muda no PW. Por isso os dois
  continuam juntos no grupo INCONSISTENTE.
- **'Em Desenvolvimento' e 'Erro de Assinatura'** são erros de mecânica, não de conceito de
  projeto. Ficam num **grupo próprio, ERRO**, com um cartão separado no painel.
- Consequência: no perfil Metrô, os dois estados saem de EM ANÁLISE e vão para o grupo ERRO, que
  continua contando no total (exige ação), como INCONSISTENTE. Block-022.
