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

## D-037 · Push do produto liberado também para a checagem agendada

*Origem: R1 · 2026-11-19 (respondida às 01:35Z; registrado pela checagem agendada das 01:56Z) · complementa a regra de push automático da ESTEIRA*

- A checagem agendada não conseguia fazer o `git push` porque a permissão pedia alguém presente.
- O dono escolheu liberar o push ("essas coisas precisam acontecer mais automáticas").
- A regra `ask` de `git push` saiu do `.claude/settings.local.json`; o push normal passou a rodar
  sem aprovação. Force-push continua pedindo confirmação.
- A ESTEIRA.md já registra isso (seção "Duas sessões, um repositório").

## D-038 · A7 entra no perfil Metrô como "Qualidade (a confirmar)"

*Origem: Q4 · 2026-11-19 (respondida às 02:29Z) · completa a D-034 (P6)*

- A classe A7 entra já no perfil Metrô com o rótulo provisório **"Qualidade (a confirmar)"**, para
  os 50 documentos do ID do PW deixarem de ficar de fora.
- O dono vai procurar o MAN de qualidade e trazer o nome certo; aí o rótulo é trocado. Block-023.

## D-039 · Indicador do procedimento específico: barras com linha de meta

*Origem: Q3 · 2026-11-19 (respondida às 02:01Z, com imagem de exemplo anexa)*

- O indicador "aprovado em até 3 revisões, meta de 80%" aparece como **gráfico de barras com uma
  linha tracejada de meta** (o dono anexou um exemplo: barras azuis e a linha "Meta" atravessando).
- Leitura: um número geral do contrato e o mesmo número em cada recorte, ao lado do limite.
  O dono acha que "meta" talvez não seja o nome certo; seria o "limite ideal".
- Cada obra terá o seu procedimento específico e o seu controle de qualidade. Por isso o limite de
  revisões e o percentual vêm do **perfil do contrato**, não do código.
- Mais para frente, quem usa deve poder configurar os gráficos: nem toda empresa nem todo gerente
  quer ver do mesmo jeito. Fica para depois; não trava esta versão.

## D-040 · Painel de visualização separado da tela de ação

*Origem: R2 · 2026-11-19 (respondida às 02:37Z) · ajusta a D-036*

- O dono quer **separar visualização de ação**. O painel (da chefia, de reunião) mostra só o que é
  produtivo para acompanhar o contrato, interativo para filtrar e mexer. Não serve para resolver
  problema.
- Um coordenador ou gerente de contrato não precisa ver que há documento com erro no painel ("fica
  até feio"). Erros e pendências não ficam à vista da chefia.
- Ao entrar com o próprio login, a pessoa cai numa **tela inicial dela**, um dashboard com
  pendências, erros e principalmente o que tem a ver com a conta dela (o que ela mesma fez).
- Consequência: o grupo ERRO (D-036) sai do painel da chefia e vai para a tela de ação. A Central
  de Pendências / tela inicial do usuário é onde se ignora, corrige ou pede a correção.
  O recorte exato (o que some do painel, o que conta no total) segue nas perguntas abertas.

## D-041 · Erro fora do painel da chefia; INCONSISTENTE fica

*Origem: S1, S2 · 2026-11-19 · detalha a D-040*

- **Correção do Claude:** a pergunta S1 falava em "cerca de 230 documentos em erro". O número estava
  errado: foi contado no histórico de análises, não na situação atual. O dono conferiu no ID do PW
  (`entrada/data.xlsx`): são **4 em Erro de Assinatura** (classes G6 e J2) e **3 em Em
  Desenvolvimento** (PEs, documentos de qualidade). O painel mostra 4 em ERRO.
- Os erros são poucos e devem ser resolvidos rápido: a pessoa chega de manhã, vê e resolve. Se houver
  reunião antes disso, quem cuida avisa. Muitas vezes o erro nem é nosso (erro de assinatura do Metrô
  num documento que vinha andando normalmente).
- **Decisão:** o painel da chefia não tem cartão ERRO. Um documento em erro aparece pela **última
  situação válida antes do erro** (o documento "vinha sendo compatibilizado normalmente" até ali).
  Sem situação anterior, conta como a situação inicial de análise do perfil. O erro aparece na tela de
  ação. Regra genérica do perfil (grupo marcado como oculto no painel), sem nada fixo.
- **S2:** INCONSISTENTE continua no painel da chefia, com cartão, fatia e barra. É erro crítico de
  projeto (o projetista não seguiu o manual) e é informação útil na reunião.

## D-042 · Próximo Marco: tela de ação e pendências

*Origem: U1, S3, S4 · 2026-11-19*

- **U1:** depois do Marco "Dados reais + painel", vem a **tela de ação e pendências**.
- **S3:** é um dashboard de controle do contrato em que o usuário participa (com mais de um contrato,
  ele troca de contrato e a tela acompanha). Visão do dono, em "janelas":
  - **erros** a corrigir;
  - **tempo de análise:** o contrato entre a Alya e o Metrô dá X dias para o cliente analisar,
    contados a partir da emissão identificada;
  - **tempo de devolução:** nós também temos um prazo para devolver o documento revisado;
  - **cronograma:** previsão de emissão de documentos (o que está para sair nesta semana);
  - **revisão:** documentos que precisam ser revisados ou estão em revisão e não foram entregues.
  - Futuro: os subcontratados. Primeiro só nós controlamos (one-sided).
- **S4:** por enquanto **todos veem tudo**. Todo mundo precisa saber dos erros e problemas do
  contrato. Mas precisa haver **registro (log) de quem fez cada coisa**: na lista de documentos com
  erro, uma coluna mostra quem lançou a informação no sistema. Não é para acusar; é controle, para
  saber a quem perguntar.

## D-043 · Regra de ouro da revisão no Metrô e o documento como pasta

*Origem: T1, T3 · 2026-11-19 · o dono pediu para gravar isto como regra fixa do perfil Metrô*

- **Série da revisão (Metrô):** cópias em análise com revisão 1, 2, 3, 4… sem fim. Aprovado → **0**.
  Mexer no aprovado → **A1, A2, A3…**; aprovado → **A**. De novo → **B1, B2…** → **B**; depois
  **C1…** → **C**, e assim por diante. (O perfil Metrô já tem isso: `preliminar` numérica,
  `original` zero depois letras, `reabertura` letra + número.)
- **Rótulo cronológico:** cada nova emissão, seja nova revisão ou nova versão, é uma revisão a mais.
  Exemplos do dono:
  - Rev 1 Ver 1 = Emissão Inicial; Rev 1 Ver 2 = Revisão 1; Rev 2 Ver 1 = Revisão 2.
  - Rev 1 Ver 1 = Emissão Inicial; Rev 2 Ver 1 = Revisão 1; Rev 3 Ver 1 = Revisão 2.
  - Rev 1 Ver 1 = Emissão Inicial; Rev 2 Ver 1 = Revisão 1; Rev 2 Ver 2 = Revisão 2.
- **"Aprovado em até 3 revisões"** se lê nesse vocabulário: aprovado até a **Revisão 3**, isto é, até
  a 4ª emissão do ciclo (Emissão Inicial + 3 revisões).
- **Documento como pasta (T3):** cada linha do ID gera uma "pasta"; as emissões e análises são as
  "subpastas". A situação do documento é a da **última atualização** dentro da pasta. Revisão 0 =
  aprovado. Se precisou revisar o 0 (A1), é como se reiniciasse: o documento volta a estar em análise
  ou revisão. Isso precisa estar bem definido porque alimenta todos os painéis.
- O dono reclamou de ter de explicar de novo: esta regra é matriz. Para outro contrato, quem
  configura precisa conseguir descrever a sua própria regra no perfil com essa mesma clareza.

## D-044 · Indicador do procedimento: leitura simples, linha "Meta"

*Origem: T2, T4 · 2026-11-19 · ajusta a D-039*

- **T2:** não criar classificação à parte para documento empacado sem aprovação. A leitura do gráfico
  (quais barras ficam abaixo da linha) já mostra o problema de uma disciplina, de um projetista ou da
  análise. No perfil Metrô, `contar_estourados_sem_aprovacao: false`.
- **T4:** a linha se chama **Meta**.

## D-045 · Sequencial do Metrô com 3 ou 4 dígitos

*Origem: V1 · 2026-11-19 · corrige uma afirmação errada do Claude*

- A pergunta V1 dizia que o Metrô exige 4 dígitos. **Errado.** O MAN-10-201 rev. 04, item 5.2.6, diz
  que o sequencial tem três ou quatro dígitos: três até 999, quatro só acima de 999. Então
  `RT-15.25.00.00-6A9-701` é válido.
- O dono lembrou que os projetos básicos do Metrô usam muito 001, 002, e que as faixas 1000, 1500,
  1700 e 2000 foram indicação do cliente.
- **Regra para o Claude:** antes de afirmar uma regra do cliente numa pergunta, rechecar o MAN e os
  dados reais.

## D-046 · Linhas defeituosas da extração do PW: avisar e reextrair, não descartar

*Origem: V2 · 2026-11-19*

- As 8 linhas que sobraram (4 com data no lugar do título e 4 desenhos do 23.17.84 com colunas
  deslocadas) são **bug da exportação do PW** ("Export Table Data"), não documentos a descartar.
- O dono contornou filtrando no PW só as disciplinas com erro e exportando de novo; o resultado saiu
  certo e está em `entrada/Correção de bug Extração ID PW.xlsx` (ver pergunta Z1).
- **Decisão:** o sistema deve **indicar que a planilha veio defeituosa** para a pessoa reextrair e
  corrigir. Não precisa de botão "descartar" ou "ignorar" para esse caso. A planilha de correção é
  mesclada às informações já importadas.

## D-047 · Ciclo do documento é um só, linear; a aprovação conta uma vez

*Origem: W1 · 2026-11-19 · complementa a D-043*

- Para o dono, o ciclo é um só: se depois do 0 veio A1, o ciclo que parecia fechado reabriu. A
  "pasta" do documento ganha novas subpastas até aprovar de novo; vale a situação da mais recente.
- **Medição:** no contrato, o DE é medido 40% na emissão e 60% na aprovação. A reabertura **não é
  cobrada de novo** do Metrô. Logo, aprovação é uma só por documento.
- **Leitura do Claude (o dono pediu opinião):** isso é compatível com o indicador atual. O indicador
  "aprovado em até N revisões" mede até a primeira aprovação (a única que conta), e a reabertura muda
  a situação do documento (volta a "em revisão/análise") sem gerar uma segunda aprovação na conta.
  Não há ciclos separados.

## D-048 · Prazos do Metrô: 15 dias úteis a partir da emissão no PW

*Origem: X1, X2, X3 · 2026-11-19 · fonte: PE-ENG-001 (70.579), anexado pelo dono na X1*

- **Prazo do cliente (X1):** PE-ENG-001 item 5.3.2 (p. 9): o Metrô tem **no máximo 15 dias úteis**,
  conforme o contrato, para comunicar o resultado da análise via PW.
- **Início da contagem (X3):** a **data de emissão no PW**.
- **Nosso prazo de devolução (X2):** o dono disse que está na mesma cláusula. O texto do PE só remete
  ao **Anexo 1** (item 5.6, p. 11), que é imagem e não foi lido automaticamente. Pendente (pergunta
  X7).
- **Indicador de prazo (PE item 5.6):** satisfatório quando, em média, **80% ou mais** dos prazos são
  cumpridos. O PE item 5.5 confirma a meta de qualidade: aprovação em até 3 revisões.
- Os prazos vêm do procedimento específico de cada empreendimento: entram no **perfil do contrato**,
  nada fixo.

## D-049 · Cronograma por planilha simples

*Origem: X4 · 2026-11-19*

- A previsão de emissão entra por **planilha**: código do documento, revisão e versão iniciais (só
  para referência; a primeira emissão é sempre Rev 1 / Ver 1) e a **data de emissão** (prevista ou
  real). Copiar e colar no Excel e importar.
- Futuro: importar exportação do MS Project.

## D-050 · Registro (log) de tudo, auditável

*Origem: X5 · 2026-11-19 · amplia a S4/D-042*

- Para ser uma ferramenta séria, **toda alteração é registrada**: importações e reprocessamentos,
  tratamento de erro, mudança no perfil, edição de documento (inclusive do ID, que é documentação
  fixa: título, classe…), emissões, análises e mudanças de situação, atualização do ID e da extração
  do PW.
- Modelo: o histórico do SharePoint ("fulano excluiu tal coisa"). Um resumo na lista e mais detalhes
  ao clicar no item.

## D-051 · "Pedir correção ao cliente": registra e gera texto de e-mail

*Origem: X6 · 2026-11-19*

- O botão registra o pedido e oferece um **texto de e-mail** para copiar (padrão). É opcional: o dono
  muitas vezes nem escreve, porque o projeto está aprovado e a obra segue, mas outros empreendimentos
  podem precisar.
- Futuro: com a IA integrada (D-035), o texto pode ser redigido por ela.

## D-052 · Retorno do painel (Y1): Marco "Dados reais + painel" não aprovado, vira ajustes

*Origem: Y1 · 2026-11-19 · conferido pelo Claude no PE-ENG-001 e no `plataforma/dev.sqlite3`*

- **Meta errada no indicador das revisões:** o PE-ENG-001 item 5.5 só diz que é satisfatória a
  aprovação **em até 3 revisões**, sem percentual. O 80% é do item 5.6 (**prazos**). O erro foi do
  Claude. O gráfico das revisões passa a mostrar quantos documentos aprovaram em 1, 2, 3, 4, 5+
  revisões, com a linha tracejada "Meta" no limite de 3. O 80% vai para o indicador de prazo (D-055).
- **Total 1106 × 827 (diagnóstico):** o previsto é a união dos IDs vigentes (D-031/D-032). Dos 1110
  documentos, 817 vêm da extração do PW; **281 vêm só do ID-15.25.00.00-6A9-1501** (faixa 2000,
  nenhum no PW; só 4 dos 293 "só nos IDs formais" têm emissão) e 12 dos IDs 1001/1002. Esse é o
  excesso. Decisão do 100% em aberto (pergunta AA1).
- **Avanço de 23,5% = aprovados / total.** O escritório mede mais alto. Fórmula em aberto (AA2).
- **Layout:** o topo (nome, sair) e o menu da esquerda ficam **sempre visíveis** ao rolar. As cores
  atuais têm contraste ruim (filtro com letra azul em fundo branco, importações, caixas de formulário
  do importar ID). Refazer o esquema de cores com contraste legível em toda a plataforma.
- **Filtros:** hoje o filtro aplica antes do botão "Aplicar". Decisão do Claude, para confirmar
  (AA3): aplicar na hora, como a tabela dinâmica do Excel, sem botão "Aplicar"; clicar de novo
  desmarca; "Limpar" continua.
- **Cartões por categoria:** além do total, mostrar o total separado por categoria (civil, sistemas,
  arquitetura, qualidade…), como na Lista Mestra (coluna MODALIDADE). A categoria vem do perfil.
- **Linhas recusadas (W1, W2, F6-1009/1010):** conferido no `ID PW.xlsx`. As linhas 53 e 54 têm
  Name `…6F6-1009`/`-1010`, mas o atributo Sequencial é 1006/1007; as linhas 137 e 138 têm Name
  `DE-…6W1-1001`/`DE-…6W2-1002`, mas Sigla RT (os registros corretos `RT-…` estão nas linhas 592 e
  593). A recusa está certa, mas a mensagem "linha deslocada" está errada: é **atributo do PW que
  diverge do Name**. A mensagem deve dizer qual campo e os dois valores.

## D-053 · Arquivo de correção é só análise; o sistema avisa e a pessoa reextrai

*Origem: Z1 · 2026-11-19 · complementa a D-046*

- `entrada/Correção de bug Extração ID PW.xlsx` serviu só para confirmar o bug. Não é importado.
- Na prática: o sistema aponta as linhas defeituosas; a pessoa corrige na planilha (ou pede à IA) e
  importa de novo pela tela. As linhas recusadas somem quando a nova importação traz a linha certa.

## D-054 · Prazos pelo contrato (cláusula 25.1.2), não pelo PE

*Origem: X7, X10 · 2026-11-19 · texto do contrato colado pelo dono*

- **Cliente:** 25.1.2.1, o Metrô analisa em no máximo **15 dias úteis** (manuais de operação,
  manutenção, software e treinamento: 30 dias). A contagem começa na data de emissão no PW (X3).
- **Nós:** 25.1.2.3, devolver o documento revisado em no máximo **15 dias (corridos)** a partir do
  Relatório de Verificação, ou seja, da data da análise do cliente.
- O PE parece errado nesse ponto (o dono notou). Os prazos e o tipo de dia (úteis ou corridos) ficam
  no **perfil do contrato**, com exceções por tipo de documento.

## D-055 · Dias úteis: feriados obrigatórios, sem digitação manual

*Origem: X8 · 2026-11-19*

- Saem da conta sábados, domingos e feriados **obrigatórios**. Os nacionais o sistema calcula sozinho
  (fixos e móveis); estaduais e municipais entram por planilha simples (data, nome) no perfil. Nada
  de cadastrar dia a dia no calendário.

## D-056 · Cronograma só com a data prevista; indicador de prazo no painel

*Origem: X9, X10 · 2026-11-19*

- A planilha de cronograma traz o código e a **data prevista**. A real vem da extração do PW.
- O indicador de prazo (80%, PE 5.6) entra no **painel da chefia**, com linha "Meta" em 80%.

## D-057 · Classe N3 é ARQUITETURA

*Origem: AA4 · 2026-11-19 (respondida no chat)*

- N3 é paisagismo e urbanismo, portanto **ARQUITETURA**. Na Lista Mestra do escritório os N3 estavam como CIVIL por
  descuido no preenchimento. No perfil Metrô: ARQUITETURA = B3, B7 e N3.
- A categoria segue a classe na grande maioria dos casos, mas a regra fica configurável no perfil (classe e sigla
  combinadas), porque há exceções, como a A9, que é de qualidade (PE, MQ) ou de ATO (RT, ID).

## D-058 · O 100% é por fase; hoje conta só o ID cadastrado no PW

*Origem: AA1 · 2026-11-19*

- O contrato da Linha 15 tem **duas fases**: na fase 1, a Alya faz os projetos executivos e a obra; na fase 2, só os
  documentos executivos. Por isso existem IDs diferentes: o **ID-15.25.00.00-6A9-1501** (faixa 2000) é da fase 2 e vai
  ser cadastrado no PW mais tarde.
- **Por enquanto, o 100% é só o ID cadastrado no PW** (a extração do ID do PW). Os IDs em Excel ficam de consulta.
- Generalização: cada ID pertence a uma **fase/escopo** configurável, e o painel pode mostrar o 100% de cada fase
  (filtro), além do total. Quem configura decide quais fontes contam no previsto.

## D-059 · Avanço = aprovados ÷ total; a medição 40/60 não entra

*Origem: AA2 · 2026-11-19 · corrige a leitura da D-047*

- O 40% na emissão e 60% na aprovação é só a **medição para o cliente**, não o progresso. Progresso = aprovados ÷
  total previsto. A impressão do escritório (perto de 70%) provavelmente era outra leitura; com o total corrigido, o
  sistema mostra o número real.

## D-060 · Filtros: aplicam na hora e aparecem numa barra com "×"

*Origem: AA3 · 2026-11-19*

- Sem botão "Aplicar". Clicar aplica; clicar de novo tira. Uma **barra horizontal** mostra os filtros ativos, cada um
  com um "×" para tirar só ele, e um botão **"Limpar todos"**.

## D-061 · Manuais: 30 dias úteis

*Origem: AA5, AA6 · 2026-11-19*

- MM, MO, MP, MQ e MU têm **30 dias úteis** de análise do Metrô (cláusula 25.1.2.1). A sigla de treinamento ainda não
  foi achada (o dono vai olhar o MAN de qualidade).

## D-062 · Nosso prazo de devolução só nos não aprovados

*Origem: AA7 · 2026-11-19*

- Disparam os 15 dias: Não Aprovado, Inconsistente e Não Conforme. Aprovado com comentário não dispara.

## D-063 · Meta de 80% vale para o cronograma e para a nossa devolução

*Origem: AA8 · 2026-11-19*

- O prazo de análise do Metrô aparece, mas **sem meta** (é do cliente). A meta passa a ser por regra de prazo no perfil.

## D-064 · Feriados num acervo por região

*Origem: AA9 · 2026-11-19*

- Feriados de São Paulo pré-carregados no perfil Metrô: 25/01 (municipal, São Paulo), 09/07 (estadual, SP) e Corpus
  Christi (municipal, São Paulo).
- Visão do dono: os feriados viram um **acervo** do programa. Quem configura escolhe a **região do contrato** (UF e
  município) e os feriados vêm sozinhos; o que alguém cadastrar fica no acervo para os próximos contratos. Mudança de
  lei é esporádica e se ajusta à mão.
- **Lembretes do dono** (pedido na AA5): o que ele adiou fica numa lista no painel para ser cobrado.

## D-065 · Os prazos estão certos; falta mostrar o quanto se atrasou

*Origem: AA10 · 2026-11-19*

- O dono confirma os números (Metrô 64,1% no prazo; nós 16,7%): a fonte é a extração atualizada e o contrato teve
  problemas reais (equipe subdimensionada, projetistas com entregas ruins). O sistema mostra de forma automática o que o
  Excel não acompanha.
- Pedido novo: **faixas de criticidade do atraso**. Passar 1 a 5 dias do prazo é diferente de passar 30 ou 60 dias. O
  painel deve mostrar quantos dos atrasados estão em cada faixa.
- Generalização: cada contrato define as **suas faixas** (limites e nomes) no perfil.

## D-066 · A cópia 0 não conta como revisão; reaberturas têm contagem própria

*Origem: AB1 · 2026-11-19*

- A Rev 0 (original emitida depois da aprovação, PE 5.3.3) aparece como **"Original (aprovado)"** e não soma revisão.
  A contagem da reabertura começa nela: A1 = Revisão 1 da reabertura.
- Ideia do dono para a melhoria do PE (não é regra ainda): um segundo parâmetro de excelência para reaberturas causadas
  por **problema não previsto em campo** (não erro de projeto). Ex.: abrir A1 e aprovar logo em A, sem A2/A3, e até duas
  reaberturas assim (A1 → A, B1 → B) ainda contam como qualidade.

## D-067 · W1 e W2 de São Mateus: os DE valem; o RT vai ser desmembrado

*Origem: AC2 · 2026-11-19*

- A pedido do cliente, os relatórios de sondagem (classes W1 e W2) viraram **DE** no PW. O RT ainda existe e não se sabe se
  será cancelado; ele vai ser desmembrado em vários DE (sondagens a trado, mista e a percussão).
- Os DE não são duplicados com sigla errada. O efeito do RT no 100% enquanto ele existir ficou para a AC6.

## D-068 · Painel abre no total; cada ID diz o que representa

*Origem: AC3 · 2026-11-19*

- Com várias fases, o painel abre **somando tudo** e o filtro "Fase" mostra o 100% de cada uma (já é o comportamento do
  block-042).
- Os IDs ficam todos num só previsto, mas quem configura diz **o que cada ID representa** (ex.: ID 1001 = arquitetura e
  civil, ID 1002 = sistemas, um ID de qualidade, o ID 1501 = fase 2 com tudo). Esse agrupamento vira filtro no painel e
  nos gráficos.

## D-069 · Escopo do ID vira lista do contrato, marcada em caixinhas

*Origem: Y2 · 2026-11-26*

- O campo livre "escopo" do ID (block-049) é trocado por uma **lista de escopos cadastrada para o contrato**: o admin
  cadastra uma vez (ex.: Arquitetura, Civil, Sistemas, Qualidade).
- Na tela do ID, a pessoa **marca caixinhas** em vez de digitar. Um ID pode ter **mais de um escopo** (o 1001 marca
  Arquitetura e Civil).
- Se faltar um escopo, ela clica em **"+ novo escopo"**: ele entra na lista e passa a valer para todos os IDs do contrato.

## D-070 · Y2 aprovada; Início e Pendências deixam de ser a mesma tela

*Origem: Y2 · 2026-11-26*

- O dono aprova os blocks 027 a 049 ("tá muito mais legível"). O Admin ainda precisa de muita mudança, mas fica para
  depois; o foco segue nas telas iniciais.
- **Início** e **Pendências** hoje são iguais. O Início passa a ser uma tela de bater o olho: **cards menores de alerta**,
  com resumos (ex.: "você tem N documentos da disciplina X pendentes", já que o cliente aprova e reprova em pacotes, por
  disciplina ou classe). A tela **Pendências** fica com o detalhe item a item (e ainda vai ser refinada: espaços vazios).
- Ideia futura, não agora: cards alimentados por fontes externas (ex.: resumo de e-mail do cliente via Outlook).
- **Atividade** (histórico de tudo): o dono gostou, mas pergunta se deve ser visível a todos ou só ao admin (no PW o
  histórico fica por documento; no SharePoint há o log geral). Fica em aberto (pergunta nova).
- Refinos visuais registrados para não passar batido: em Atividade, o rótulo "Pessoa" sobrepõe a caixa "Contrato" (o
  clique pega o campo errado); no Painel, o título com o nome do contrato invade o card ao lado, e um nome longo
  extrapolaria. Os enquadramentos precisam aguentar nomes grandes.

## D-071 · Motivo da reabertura em lista fixa; indicador da reabertura resolvida já entra, sem meta

*Origem: AB2 e AB3 · 2026-11-26*

- Cada reabertura de documento aprovado (A1, B1…) ganha um **motivo**, escolhido numa **lista fixa** (sem interpretação de
  texto, porque no web app não há LLM por trás): problema de campo, erro de projeto, pedido do cliente, outro. Esses
  parâmetros servem depois para análises e visualizações para diretoria e reunião. Se precisar mudar, adequa-se.
- O indicador **"reabertura resolvida numa revisão só"** (A1 → A, até 2 reaberturas assim) **já entra no painel, sem
  meta**, como informação para apoiar a revisão do PE. Os parâmetros (quantas reaberturas, quantas revisões por
  reabertura) ficam **configuráveis no perfil**, porque cada empresa/contrato tem o seu padrão de qualidade.
- Visão do dono: o PE certo seria a fonte, e alimentar o sistema com um PE é trabalho de início de contrato. É preciso
  criar meios fáceis de imputar essas regras (ex.: uma IA resume o PE num formato que o programa entende), em vez de um
  formulário gigante. Fica como direção para o perfil/configuração.

## D-072 · F6-1006/1007 de São Mateus: o código certo é 1006/1007

*Origem: AC1 · 2026-11-26*

- Os dois desenhos de sinalização e RTD das baias da SPTrans são **DE-15.23.17.84-6F6-1006 e -1007**. O Name no PW
  (-1009/-1010) está errado; o atributo Sequencial e o nosso ID estão certos. Os documentos ainda não foram emitidos
  (travados por aprovação de órgão), por isso o erro passou. O dono vai pedir a correção no PW.
- O ID do PW tem o 1008 (fibra óptica de RTD), que não está no ID em Excel: foi pedido um **ID parcial** e o ID completo
  não foi atualizado. Isso deve acontecer mais vezes (documento no ID do PW que não está no ID completo).
- Lição para a mensagem do sistema: quando Name e atributo divergem, nem sempre o atributo é o errado.

## D-073 · F6-1030 e 1306–1309 ainda vão sair; o certo é o 100% pelo nosso ID atualizado

*Origem: AC5 · 2026-11-26*

- Esses desenhos existem e vão ser emitidos; faltou pedir um ID parcial no PW (travados por aprovação de órgão).
- Visão do dono: o certo é o 100% ser contado pelo **nosso ID atualizado** (ID-15.25.00 1001, 1002 e 1501, que viraram
  faixa 2000 e ainda precisam de correção). Às vezes nós prevemos documentos que o cliente ainda não aceitou: é falha de
  processo, mas acontece em todo lugar. Como isso convive com a D-058 (hoje só o PW conta) ficou para a pergunta AF2.

## D-074 · Documento só muda quando muda oficialmente; cancelamento tem dono

*Origem: AC6 · 2026-11-26*

- O RT de sondagem de São Mateus **conta no 100% até ser cancelado**. Regra geral: o documento só muda quando a mudança é
  oficial (no Metrô, quando muda no PW). Exceções existem e são do contrato/empresa (ex.: "para aprovação" conta como
  aprovado).
- O sistema vai precisar de um **controle de cancelamento**: no ID, filtrar e selecionar documentos para cancelar, com
  confirmação ("tem certeza?"), registrado no login de quem cancelou. Não é qualquer um: no mínimo um admin. Sem
  aprovação formal por e-mail.

## D-075 · Faixas de atraso da Linha 15 confirmadas; atraso crítico na Minha mesa

*Origem: AD1 e AD2 · 2026-11-26*

- Faixas: **até 5 / 6–30 / 31–60 / mais de 60 dias** (as provisórias do block-048 ficam valendo).
- Além do painel, o atraso aparece na **Minha mesa (Pendências), do mais atrasado para o menos**, com etiqueta de cor da
  faixa. No Início, um card de resumo: "N documentos atrasados", quantos em cada cor.

## D-076 · Atividade só para admin; feriados só o admin da plataforma; motivo por admin e editores

*Origem: AE1, AC4 e AE3 · 2026-11-26*

- A tela **Atividade** (histórico geral) fica só para admin. O histórico de cada documento continua na pasta dele.
- O **acervo de feriados** por região é cadastrado e corrigido só pelo **admin da plataforma** (superusuário), não pelo
  admin de um contrato.
- O **motivo da reabertura** é informado por admin e editores do contrato (como o block-051 fez).

## D-077 · Pacote do Início = classe completa do código, com o nome

*Origem: AE2 · 2026-11-26*

- O cliente aprova e reprova por pacote. No card do Início o pacote aparece com o **código completo da classe e o nome**,
  ex.: **"6G6 · Terraplenagem"**, porque muita gente não decora as classes e o número da etapa (6 = executivo no Metrô,
  3/4 = básico; na SPObras o 5 é executivo) evita confusão se um contrato tiver mais de uma etapa.
- Genérico: o perfil diz quais caixas do código formam o pacote (no Metrô, etapa + classe) e de qual caixa vem o nome.

## D-078 · Cancelado vindo do PW sai sozinho; contratos sem PW precisam de outro caminho

*Origem: AF1 · 2026-11-26*

- Quando a extração de situação do PW traz **"Cancelado"**, o documento **sai do 100% sozinho**, sem confirmação de admin,
  e **fica registrado** qual importação cancelou (Atividade). No Metrô isso resolve, porque o PW é a fonte oficial.
- Questão do dono para contratos **sem PW/GED**: como informar os cancelados? Opções levantadas por ele: marcar
  manualmente no web app, selecionando **mais de um documento** de uma vez e mudando o status de todos; ou enviar uma
  **tabela simples de 2 colunas** (código e situação) que o programa lê e aplica. Fica em pergunta (AH1), com a visão de
  um programa que se adapta a contratos e formas de preencher diferentes.

## D-079 · Cancelar pelo sistema: motivo de lista + observação livre

*Origem: AF2 · 2026-11-26*

- O admin que cancela pelo sistema informa um **motivo de uma lista** (para filtrar e analisar) **e uma observação em
  texto livre** (informação extra para o futuro).
- Motivos sugeridos pelo dono: desmembrado, substituído, pedido do cliente, fora do escopo, inviável (ex.: prospecção em
  campo mostrou que não dá para executar). Ele pediu mais sugestões. Lista proposta pelo Claude, implementada no
  block-057 e posta para confirmação (AH2): desmembrado em outros documentos, incorporado a outro documento, substituído
  por outro documento, pedido do cliente, fora do escopo, inviável (constatado em campo), mudança de solução de projeto,
  duplicado/código em dobro, outro (observação obrigatória).

## D-080 · O 100% é o nosso ID; o ID do PW vira contraprova

*Origem: AF4 · 2026-11-26*

- Documento que está no **nosso ID atualizado** e ainda não no ID do PW (ex.: F6-1030 e 1306–1309) **conta no 100%**,
  com o aviso **"falta no PW"** na Pendências. O contrário (no PW e fora do nosso ID, ex.: 1008) também aparece para tratar.
- Visão do dono: em contrato sem um segundo ID, o que vale é o **ID combinado entre cliente e contratada** (normalmente
  feito pela contratada). Onde houver um segundo ID como contraprova (Metrô/PW), o sistema gera **alerta de
  incompatibilidade**, sem trocar a fonte do 100%.
- Para extrações de outros GEDs, o dono quer um **formato padrão** que os usuários aprendem a preencher (ou pedem a uma IA
  para preencher) e que o programa sempre lê do mesmo jeito. Liga com a D-081.

## D-081 · Contrato sem PW: cancela pela tela e também por tabela simples

*Origem: AH1 · 2026-11-26*

- Os dois caminhos: a **tela** (seleção múltipla na lista de Documentos, block-057) para o dia a dia, e uma **tabela
  simples (código, situação)** que vira o **importador genérico de situação** para contratos sem PW, com prévia antes de
  aplicar. Serve também para aprovado, em análise etc.
- O dono não descarta personalização por contrato, mas pede que se **defina uma decisão e se siga**: o padrão é a tabela
  de duas colunas; variações viram opção do perfil só se aparecer necessidade real.

## D-082 · Cancelado por engano volta pelas mãos do admin, com registro

*Origem: AF3 · 2026-11-26*

- O **admin reativa** o documento cancelado pelo sistema, com a mesma confirmação e o mesmo registro do cancelamento
  (quem, quando, motivo da reativação). Cancelado vindo do PW só volta quando o PW mudar.
- Ideia do dono, ainda sem decisão: **backups automáticos** (diários ou de hora em hora) que um admin possa restaurar
  ("ChronoBreak"). Se for exagero, basta o admin poder desfazer os status importantes. Fica em pergunta.

## D-083 · Name errado no PW: linhas ficam recusadas até alguém corrigir

*Origem: AF5 · 2026-11-26*

- As linhas dos F6-1009/1010 (certo 1006/1007) **ficam recusadas com a mensagem neutra** "Name e atributo divergem"
  (já entregue no block-056) até alguém corrigir: o dono corrige manualmente no PW, ou chega outra extração, ou uma
  planilha no formato padrão (D-081).

## D-084 · Os IDs 1001, 1002 e 1501 viraram um ID só (corrigida pela D-089)

*Origem: AF6 · 2026-11-26*

- Não foi só o 1501: **todos** viraram um único ID da série 2000, inclusive o 1501. O dono pôs o ID atualizado em
  `entrada/` (`ID-15.25.00.00-6A9-2001-1.xlsx`). O novo passa a ser o ID vigente; os antigos ficam como histórico.

## D-085 · Indicador de reabertura da Linha 15: até 2 reaberturas, 1 revisão cada

*Origem: AG1 · 2026-11-26*

- Confirmados os parâmetros que estavam provisórios no `metro.yaml`: `max_reaberturas: 2`,
  `max_revisoes_por_reabertura: 1` (A1 → A conta como resolvida; A1 → A2 → A não).

## D-086 · Motivos de cancelamento ficam como estão e vão para o perfil

*Origem: AH2 · 2026-11-26*

- A lista do block-057 fica, mas passa a ser **do perfil do contrato** (configurada pelo admin), começando por ela.

## D-087 · Início = "Minha mesa" no layout que o dono desenhou

*Origem: AG2 · 2026-11-26*

- O dono anexou um modelo da tela inicial (não precisa ser idêntico, mas é o layout que ele quer ver e continuar vendo
  conforme entrarem mais informações). Título **"Minha mesa"**, subtítulo "Visão geral do contrato, alertas e próximos
  acompanhamentos", seletor de contrato à direita.
- Linha 1, quatro indicadores: **Pendências abertas**, **Em análise do cliente**, **Atrasados** (destaque de alerta) e
  **Aprovados na semana** (últimos 7 dias).
- Linha 2: **Pendências por pacote** (código da classe · nome, quantidade, barra e etiqueta Crítico/Atenção/Em dia),
  **Atraso por faixa** (as faixas do perfil com contagem) e **Análise do cliente** (documentos com etiqueta "Atrasado há N
  dias" ou "Em análise", código e título, link para a pasta).
- Linha 3: **Pacotes em destaque**, **Atividade recente**, **Mensagens / Integrações** (espaço reservado "em breve", para
  e-mails e alertas futuros) e **Ações rápidas** (Ver pendências, Abrir documentos, Importar PW).
- Ordem: o que estoura prazo e o que pede ação vem antes; pacotes na sequência (próximo da opção recomendada).

## D-088 · Backup diário do banco inteiro, restaurado só pelo admin da plataforma

*Origem: AI1 · 2026-11-26*

- Uma **cópia automática por dia do banco inteiro** (todos os contratos, documentos, revisões, importações e registros),
  guardando as **últimas 30 cópias** (30 dias). Não é "30 documentos": cada cópia é o sistema todo naquele dia.
- O objetivo é **segurança contra pane** (disco, arquivo corrompido, erro grave). Restaurar volta tudo ao dia escolhido;
  por isso só o **admin da plataforma (superusuário)** restaura, com confirmação. O desfazer do dia a dia continua pelas
  reativações com registro (D-082).

## D-089 · O ID 2001 substitui só o 1501; filtro por escopo e por classe

*Origem: AI2 · 2026-11-26 · corrige D-084*

- O dono explicou que o **2001 substituiu o 1501**: só mudaram os códigos, e ele deixou os dois em `entrada/` para mostrar
  isso; o 1501 será apagado depois. Conferido nos arquivos: 279 códigos iguais; só o MC-15.25.00.00-6I5-1501 e o
  RT-15.25.00.00-6C3-1501 viraram -2001. Os IDs 1001 e 1002 **não estão** no 2001 (o que acontece com eles fica em
  pergunta). Isso corrige o "todos viraram um ID só" da D-084.
- Escopo desta fase: o ID cobre **arquitetura/civil e sistemas**; não tem qualidade (qualidade é da execução, e esta obra
  só produz os projetos executivos). É particularidade desta obra, não regra.
- **Filtro: os dois.** O painel filtra por escopo **e** por classe; quem quiser ver só uma classe filtra por ela.

## D-090 · Planilha padrão de situação: código, revisão, situação, data, mais colunas opcionais

*Origem: AI3 · 2026-11-26*

- Colunas base: **código, revisão, situação, data** (revisão vazia = última; data vazia = data da importação).
- O dono pede **mais colunas no modelo**, porque outros contratos podem ter informações que esta obra não tem: quem não
  tiver, **deixa em branco**. Toda coluna além do código é opcional.

## D-091 · "Falta no PW" é pendência com ação

*Origem: AI4 · 2026-11-26*

- Documento do nosso ID que ainda não está no ID do PW entra na **Pendências** como "pedir inclusão no PW", com quem
  resolveu e quando, como os outros erros. Continua contando no 100% (D-080).

## D-092 · "Falta no nosso ID" fica fora do 100%; comparação com o ID do cliente é opção do perfil

*Origem: AI5 · 2026-11-26*

- Documento que está no ID do PW mas não no nosso ID **não conta no 100%** e vira pendência "falta no nosso ID" até alguém
  incluir no nosso ID ou cancelar.
- Ideia do dono, aceita: o perfil do contrato ganha a opção **"comparar com o ID do cliente (GED)"**, ligada ou desligada.
  Ligada, valem a comparação e as pendências "falta no PW" / "falta no nosso ID" (D-091 e esta). Desligada (contrato sem
  GED, só o nosso ID), não há comparação nem esses avisos. Linha 15 fica ligada.

## D-093 · Planilha padrão de situação: admin e editor aplicam

*Origem: AI6 · 2026-11-26*

- Mesmo fluxo da importação do PW: admin e editor sobem, veem a prévia e aplicam; tudo registrado na Atividade.

## D-094 · Card "Mensagens / Integrações" começa pelos alertas do sistema

*Origem: AI7 · 2026-11-26*

- A primeira coisa no card da Minha mesa são os **alertas gerados pelo próprio sistema** (importação nova, prazo vencendo
  amanhã, documento cancelado). E-mail do contrato fica para depois, porque depende de liberação da TI.

## D-095 · Nosso ID = 1001 + 1002 + 2001; o 1501 sai da pasta

*Origem: AJ1 · 2026-11-26 · completa a D-089*

- Os IDs **1001 e 1002 continuam vigentes**. O nosso ID passa a ser **1001 + 1002 + 2001**.
- O dono confirmou que vai **excluir o 1501 da pasta**: o 2001 só o substitui com códigos novos, o conteúdo é o mesmo.
  Entendido e conferido (279 documentos iguais; só MC-6I5 e RT-6C3 mudam de -1501 para -2001). O 1501 já importado fica
  no sistema como **histórico** (substituído pelo 2001), sem contar no previsto, e sumir do `entrada/` não apaga nada.

## D-096 · Planilha padrão: observação, GRD, data de envio e data de retorno; colunas por perfil

*Origem: AJ2 · 2026-11-26 · completa a D-090*

- Colunas opcionais do modelo: **observação, GRD, data de envio, data de retorno** (todas podem vir em branco).
- Visão do dono: as colunas devem ser **configuráveis pelo admin** na pré-configuração do contrato. Para quem usa PW, o
  layout de colunas da extração do PW pode ser uma **opção pronta** (preset); para outros sistemas, ou sem sistema, o
  admin monta as colunas. Algumas colunas são **padrão do nosso processo** (GRD, data de envio, data de retorno...), por
  exigência de auditoria, e não do cliente. A Lista Mestra `.xlsm` atual tem muitas dessas colunas, várias em branco hoje.
- Primeiro passo (block-062): o modelo fixo base + opcionais acima. A configuração de colunas pelo admin e o preset PW
  ficam como continuação.

## D-097 · Backup em pasta configurável; padrão local; pode ser o SharePoint sincronizado

*Origem: AJ3 · 2026-11-26 · completa a D-088*

- O admin aponta a pasta do backup; sem configuração, usa `backups/` ao lado do sistema. Aviso no painel se falhar.
- O dono lembra que a pasta pode ser o **SharePoint da empresa daquele contrato**, sincronizado no Windows (fica como uma
  pasta comum no disco), o que já dá cópia fora da máquina.

## D-098 · "Comparar com o ID do cliente" é pré-configuração do contrato, não um liga/desliga do dia a dia

*Origem: AJ4 · 2026-11-26 · esclarece a D-092*

- O dono estranhou a pergunta: contrato que **tem** ID do cliente (GED, aqui o PW) não vai desligar a comparação. A opção
  existe para o admin **montar o ambiente de cada contrato**: quem tem GED liga, quem não tem deixa desligada. Não é
  função para ficar ligando e desligando.
- Consequência técnica (escolha do Claude, sem nova pergunta): as pendências "falta no PW" / "falta no nosso ID" são
  **calculadas ao vivo** a partir dessa opção; não há tratamento especial para "desligar com pendência aberta".

## D-099 · A7 e os PE/MQ da A9 são QUALIDADE neste contrato; não existe MAN de qualidade

*Origem: chat com o dono · 2026-11-27 · fecha a D-038 e o lembrete l01; confirma a D-057*

- O dono informou que **não existe MAN de qualidade**: a busca pelo manual (D-034/P6, D-038) se encerra aqui.
- Para **este contrato**, a classe **A7** e os documentos de qualidade da **A9** (PE e MQ) são **QUALIDADE**, e a
  plataforma os categoriza assim. O rótulo provisório "Qualidade (a confirmar)" da A7 vira definitivo: **"Qualidade"**.
- Os RT/ID da A9 continuam como estão (ATO), conforme a D-057. A sigla do manual de treinamento (D-061) não foi
  tratada nesta resposta e continua a confirmar.

## D-100 · Esteira contínua: sem resposta nova, a esteira executa o roadmap

*Origem: chat com o dono · 2026-11-27 · amplia a D-012/D-013 e a regra "Nada para a esteira"*

- O dono achou o avanço lento por depender só das respostas dele ("precisa ter uma certa continuidade").
- Nova regra: **havendo respostas, a esteira executa as respostas; não havendo, executa o roadmap** e vai criando
  perguntas de **avaliação** do que entregou. As avaliações do dono geram ajustes e novas perguntas, em laço.
- O dono pesou os dois lados: o programa fica pronto mais cedo para ele criticar, mas pode gastar em algo que ele não
  quer. Por isso a esteira trabalha em fatias pequenas e revisáveis (ver ESTEIRA.md, "Autorização atual").

## D-101 · Minha mesa aprovada; cards precisam se explicar e abrir só o que mostram

*Origem: AG3 · 2026-11-27 · fecha a aprovação do Início (block-059/064)*

- O dono **aprovou** a Minha mesa e quer continuar avançando.
- **Clareza dos cards:** um funcionário do escritório não entendeu o card "Atrasados" ("é a gente que está atrasado? quem
  é?"). Os cards têm de dizer de quem é o atraso e o que contam. O dono vai testar a compreensão com usuários no futuro.
- **Clique filtra:** ao clicar num card, a tela deve mostrar **só aquilo** (como "maximizar" o card), mesmo dentro de
  Pendências. Hoje só "Em análise do cliente" faz isso; "Atrasados" abre Pendências inteira.
- Escolha do Claude, a confirmar (pergunta AL1): "Atrasados" passa a separar **do cliente** (análise do cliente vencida)
  e **nossos** (devolução nossa vencida), e o clique abre uma lista só dos atrasados, com essa separação.

## D-102 · O escopo de cada documento vem da classe, ligada no perfil

*Origem: AJ5 · 2026-11-27 · completa a D-089 e a D-095*

- Com o 2001 juntando arquitetura/civil e sistemas num arquivo só, o escopo não pode mais vir só do ID.
- O admin liga **cada classe a um escopo** no perfil do contrato (ex.: classes de sistemas → Sistemas). Vale para todo
  contrato. O filtro por escopo (D-089) passa a usar essa ligação; documento de classe sem escopo ligado continua usando
  o escopo do ID de onde veio (escolha do Claude, a confirmar).

## D-103 · Os dois códigos -1501 nunca foram emitidos

*Origem: AK1 · 2026-11-27 · fecha a dúvida da D-095*

- O MC-15.25.00.00-6I5-1501 e o RT-15.25.00.00-6C3-1501 **nunca foram emitidos**: só saem do previsto, sem ligar histórico
  ao -2001. Nada a fazer no sistema além do que o block-060 já faz.

## D-104 · Alertas da Minha mesa: todos veem tudo; abas por perfil e atividades da equipe vêm depois

*Origem: AK2 · 2026-11-27 · completa a D-094*

- Os alertas do sistema no card "Mensagens / Integrações" aparecem **para todos** do contrato, na mesma lista.
- Ideia nova do dono: haverá **abas personalizadas por perfil**, que ele mesmo vai configurar, incluindo um **dashboard
  de atividades da equipe** (um gerenciador de engenharia tem funcionários, e com eles atividades e pendências). Fica
  registrada como frente nova do roadmap, ainda sem desenho.

## D-105 · GRD se faz no sistema; GRD da planilha que não existe no sistema grava e avisa

*Origem: AK3 · 2026-11-27 · completa a D-096*

- Resposta: **grava e avisa** (o número fica como texto na revisão e nasce a pendência "GRD sem remessa no sistema").
- Visão do dono: as GRDs devem ser feitas **dentro do sistema**, que concentra tudo num lugar só. Uma GRD "offline" é
  estranha, e ele pede para **analisar se a coluna GRD na planilha padrão precisa existir**. Fica em pergunta (AM3) antes
  de implementar a pendência; por ora a coluna continua aceita e ignorada.

## D-106 · Data de retorno é a data da análise do cliente

*Origem: AK4 · 2026-11-27 · completa a D-090/D-096*

- "Data de retorno" é a data em que o cliente entregou a análise, ou seja, **a mesma data da situação**. Na planilha
  padrão, se a coluna "Data" vier vazia e "Data de retorno" vier preenchida, usa-se a data de retorno.

## D-107 · Colunas da planilha montadas no perfil do contrato; o preset tem o nome do sistema de origem

*Origem: AK5 · 2026-11-27 · completa a D-096*

- O admin monta as colunas **no perfil do contrato**, junto com o resto da pré-configuração.
- O dono perguntou: "preset PW? e se for outro GED, ou nenhum?". Entendimento do Claude, a confirmar (AM4): o preset é só um
  modelo pronto com o nome do sistema de onde vem a extração (PW hoje, outro GED amanhã); contrato sem GED usa a planilha
  padrão do próprio sistema, sem preset.

## D-108 · Card de atraso: "Análise atrasada" (cliente) e "Revisões atrasadas" (contratada)

*Origem: AL1 · 2026-11-27 · ajusta a D-101 e o block-065*

- O dono quer os nomes **"Análise atrasada"** e **"Revisões atrasadas"**: assim fica claro que análise é do cliente e que
  revisão atrasada é da contratada. Substituem "do cliente" e "nossos" no card e na lista dos atrasados.

## D-109 · Clicar num card do Início abre uma seção mais específica dentro de Pendências

*Origem: AL2 · 2026-11-27 · detalha a D-101*

- O clique num card do Início **não** volta à página de Pendências inteira: leva a uma **seção específica dentro de
  Pendências** ("subpasta"), com mais informação e espaço para mais funções e layout próprio. Ex.: Início → Atrasados abre
  Pendências › Atrasados, com a lista (documento, título, revisão, há quantos dias); clicar num grupo dali desce mais um
  nível (Pendências › Atrasados › Revisões atrasadas).
- O card "Pendências abertas" abre Pendências › Abertas, com um resumo por tipo; cada tipo abre a sua lista (nossa
  devolução, cronograma, linhas recusadas...).
- Quem quer a página de Pendências normal clica em **Pendências** no menu.

## D-110 · Coluna GRD da planilha padrão: só para histórico antigo

*Origem: AM1 · 2026-11-27 · ajusta a D-105*

- Resposta: **só para histórico antigo**. A coluna GRD fica na planilha padrão para trazer GRDs **de antes do sistema**:
  o número é gravado como texto ("GRD anterior ao sistema"), **sem pendência**, só para registrar que existe e está
  regularizada. As GRDs futuras nascem pela tela de GRD do sistema.
- Ideia do dono para depois (frente nova, sem desenho): trazer GRDs antigas (normalmente físicas, em PDF) para dentro do
  sistema por extração assistida — o PDF vira texto (com ajuda de IA), num formato padrão que o sistema lê e usa para
  preencher a GRD daquele documento. Alternativa simples que ele também aceita: só gravar o número pela coluna.

## D-111 · O modelo pronto de colunas leva o nome do sistema de origem

*Origem: AM2 · 2026-11-27 · confirma a D-107*

- Confirmado: o admin escolhe "Extração do PW", "Extração do <outro GED>" ou "Planilha padrão" e pode ajustar as colunas.
  Contrato sem GED usa a planilha padrão do próprio sistema.

## D-112 · Atividades da equipe começam por tarefas livres, que podem se ligar a documentos

*Origem: AM3 · 2026-11-27 · detalha a D-104*

- Primeira fatia: **tarefas com responsável e prazo**, que não precisam estar ligadas a documento, mas **podem** estar
  (um mix de tarefas livres e tarefas ligadas ao que existe no sistema).

## D-113 · Toda classe tem escopo; o escopo pode depender também do tipo de documento

*Origem: AM4 · 2026-11-27 · substitui a "escolha do Claude" da D-102*

- Para o dono, **toda classe precisa ter escopo**, definido já na configuração do contrato, assim como um arquivo que deve
  ficar na pasta A precisa estar na pasta A. Classe sem escopo ligado: **"Sem escopo" + pendência** para o admin ligar.
  O documento **não** herda o escopo do ID.
- O escopo de uma classe **pode mudar conforme o tipo de documento**. Exemplo do Metrô: MQ em A9 é escopo de Qualidade;
  outros A9 são documentos complementares ou ATOs. O perfil precisa permitir separar o escopo por classe **e** tipo.

## D-114 · Lista Mestra definitiva começa pela tela da lista

*Origem: AM5 · 2026-11-27 · detalha a D-100 / m06*

- Primeira fatia: **uma tela com uma linha por revisão e as colunas da planilha, com filtro e busca**. Exportar em Excel
  vem depois.

## D-115 · Card "Minhas tarefas": cada pessoa vê o que é dela; o gestor vê a equipe

*Origem: AM6 · 2026-11-27 · corrige o entendimento da D-104*

- O dono **não** quis dizer abas configuradas por papel. A personalização é: cada pessoa tem, logo de cara, um card com
  **as tarefas direcionadas a ela**; todos continuam vendo os outros cards de pendência. O gestor vê as tarefas de quem
  ele gere, e quem está acima do gestor também. Pode ser o admin quem atribui.

## D-116 · Antecedência do alerta de prazo vencendo fica no perfil (padrão 3 dias)

*Origem: AM7 · 2026-11-27*

- O admin define no perfil do contrato quantos dias antes o alerta de prazo vencendo aparece; padrão de 3 dias.

## D-117 · Marco 12 começa por editar o título do documento na pasta (escolha do Claude, a confirmar)

*Origem: esteira contínua (D-100) · 2026-11-27 · confirmação na avaliação do block-069*

- Com as frentes de Pendências e Lista Mestra aguardando avaliação/respostas (AN1–AN8), a esteira abre o Marco 12
  (edição e correção de documento) pela menor fatia: **editar o título** na pasta do documento, só staff/admin do
  contrato, com **motivo obrigatório** e registro na Atividade (D-050).
- A reimportação do ID **não** sobrescreve o título editado (comportamento atual: diferença vira "Título divergente").
- Classe, disciplina e demais campos ficam para depois da avaliação.

## D-118 · Marco 16 começa por um resumo executivo imprimível (escolha do Claude, a confirmar)

*Origem: esteira contínua (D-100) · 2026-11-27 · confirmação na avaliação do block-070*

- Com Pendências, Lista Mestra e Marco 12 esperando respostas/avaliação (AN1–AN8, AO1–AO2, AP1), a esteira abre o
  Marco 16 pela menor fatia: **uma página de resumo por contrato, para imprimir ou salvar em PDF pelo navegador**,
  sem biblioteca de PDF nova.
- Os números vêm do Painel e das Pendências que já existem (avanço, previstos, aprovados, em análise, atrasados por
  lado, avanço por disciplina e trecho). Quem vê: quem participa do contrato.

## D-119 · Marco 17 começa por guardar uma "foto" dos números do Painel (escolha do Claude, a confirmar)

*Origem: esteira contínua (D-100) · 2026-11-27 · confirmação na avaliação do block-071*

- Com Pendências, Lista Mestra, Marco 12 e Marco 16 esperando respostas/avaliação (AN1–AN8, AO1–AO2, AP1, AQ1), a
  esteira abre o Marco 17 (snapshots) pela menor fatia: **botão "Guardar foto de hoje" no Painel**, para staff/admin
  do contrato, que grava os números gerais do Painel (avanço %, previstos, emitidos, aprovados, em análise, pendentes,
  cancelados, atrasados por lado). Uma foto por contrato e por dia: guardar de novo no mesmo dia substitui.
- Página **"Fotos do contrato"** com a lista das fotos e a diferença de cada uma para a anterior. Sem gravação
  automática mensal e sem gráfico nesta fatia. Tabela nova (justificada: histórico não existe em outro lugar).

## D-120 · Marco 18 começa por uma tela "Contratos" só de leitura (escolha do Claude, a confirmar)

*Origem: esteira contínua (D-100) · 2026-11-27 · confirmação na avaliação do block-072*

- Com os Marcos 12, 16 e 17 esperando avaliação (AP1, AQ1, AR1) e Pendências e Lista Mestra esperando respostas, a
  esteira abre o Marco 18 (Gestão de Contratos) pela menor fatia: página **"Contratos"** no menu, só para staff,
  com uma linha por contrato (código, nome, cliente, ativo, perfil, quantas pessoas participam por papel, quantos
  documentos em conta) e links para o Painel, a Lista Mestra do contrato e a edição no admin.
- Ao abrir um contrato na tela: quem participa (nome, papel, ativo). Criar, editar, ativar e desativar continuam no
  admin nesta fatia. Sem tabela nova.

## D-121 · Marco 20 começa por um guia "Como usar a Plataforma" (escolha do Claude, a confirmar)

*Origem: esteira contínua (D-100) · 2026-11-27 · confirmação na avaliação do block-073*

- Com os Marcos 12, 16, 17 e 18 esperando avaliação (AP1, AQ1, AR1, AS1), a esteira abre o Marco 20 (Preparação
  para apresentação) pela menor fatia, só documentação: o `README.md` da raiz deixa de descrever o Streamlit como
  produto principal e passa a apresentar a Plataforma Django (o que é, como ligar, quais telas existem, quem vê cada
  uma), com o Streamlit citado como legado; e um guia novo `docs/GUIA_DE_USO.md`, tela por tela, em linguagem de
  usuário, com os nomes reais dos menus. Sem código de produto, sem prints e sem changelog nesta fatia.

## D-122 · Marco 14 (GRDs) começa por criar e consultar GRD no sistema (escolha do Claude, a confirmar)

*Origem: esteira contínua (D-100) · 2026-11-27 · confirmação na pergunta AT2 e na avaliação do block-074*

- D-105 e D-110 dizem que as GRDs futuras nascem pela tela de GRD do sistema, e o menu lateral mostra "GRDs · Em
  breve". Com a Lista Mestra esperando AO1/AN2 e as tarefas esperando AN3/AN4/AN8, a esteira abre a primeira fatia
  de GRDs na Plataforma Django, a menor versão usável: criar uma GRD do contrato (número sequencial por contrato,
  data, destinatário em texto livre, observação) com os documentos colados como lista de códigos (cada código pega a
  última emissão), listar as GRDs, abrir o detalhe imprimível e ver na pasta do documento em que GRD cada revisão saiu.
- Fora desta fatia: cópias por formato (A0–A4/Digital), distribuição por setor (AN2), recebimento por token, GRD
  antiga como histórico (D-110/AN6) e editar/cancelar GRD.

## D-123 · Marco 13 (Conciliação Assistida) começa pelos títulos diferentes do ID (escolha do Claude, a confirmar)

*Origem: esteira contínua (D-100) · 2026-11-27 · confirmação na pergunta AU2 e na avaliação do block-075*

- Com GRDs (block-074) em avaliação, Lista Mestra esperando AO1/AN2 e Tela de ação esperando AN3/AN4/AN6/AN7/AN8, a
  esteira abre a primeira fatia do Marco 13 na Plataforma Django. Desde o block-069 a reimportação do ID não
  sobrescreve o título do documento, então título do ID vigente e título do documento podem ficar diferentes sem
  ninguém ver.
- Fatia: uma seção nova em Pendências, "Título diferente do ID", com os documentos cujo título no ID vigente (item
  não excluído do índice não substituído) difere do título do documento (comparação sem diferença de maiúsculas e
  espaços nas pontas). Cada linha mostra os dois títulos e duas ações: "Usar o título do ID" (troca o título pelo
  mesmo caminho do block-069, com motivo automático citando o ID, e registra na Atividade) e "Manter o atual"
  (o "Ignorar" já existente das Pendências, com motivo).
- Fora desta fatia: outras divergências (atributos, situação), ações em lote e "enviar para revisão posterior".

## D-124 · Marco 19 (Auditabilidade) começa por baixar a Atividade em planilha (escolha do Claude, a confirmar)

*Origem: esteira contínua (D-100) · 2026-11-27 · confirmação na pergunta AV2 e na avaliação do block-076*

- A Plataforma já guarda o histórico de cada mudança (Atividade, com filtros por pessoa, ação, período e código, e o
  bloco "Ações e Atividade" na pasta do documento). O que falta para auditoria é levar esse registro para fora: hoje
  ele só existe na tela.
- Fatia: na Atividade, "Baixar planilha (CSV)" com exatamente os eventos filtrados na tela (todos, sem paginação),
  em UTF-8 com `;`, para abrir direto no Excel. Mesma permissão da tela.
- Fora desta fatia: Excel formatado (.xlsx), PDF, registro de quem viu/baixou e trilha de leitura.

## D-125 · Marco 15 (GED/PW) segue pelo histórico de importações do contrato (escolha do Claude, a confirmar)

*Origem: esteira contínua (D-100) · 2026-11-27 · confirmação na pergunta AW1 e na avaliação do block-078*

- Os importadores do Marco 15 já existem (situação do PW no block-019, situação por planilha padrão no block-062),
  com prévia antes de aplicar e a tela de linhas recusadas. Falta ver, depois, o que foi importado em cada contrato.
- Fatia: tela "Histórico de importações" do contrato, só leitura, com uma linha por importação (ID, situação e
  cronograma), a mais recente primeiro: data, tipo, arquivo, quem importou e os contadores, com link para as recusadas.
  Mesma permissão da tela de recusadas. Sem mudança no banco.
- Fora desta fatia: desfazer uma importação (rollback por lote), comparar dois lotes e baixar o histórico em planilha.
