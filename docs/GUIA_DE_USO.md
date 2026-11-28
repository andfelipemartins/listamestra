# Guia de uso da Plataforma

Este guia descreve as telas presentes na Plataforma. O acesso depende do login, do indicador de usuário **staff** no Django e, nas áreas de contrato, de uma participação ativa.

**Staff** é uma permissão da plataforma e não significa, por si só, “Administrador do contrato”. Os papéis disponíveis no contrato são **Administrador do contrato**, **Equipe técnica**, **Projetista externo** e **Chefia / coordenação**.

## Entrar na Plataforma

**Título:** `Acesse sua conta`  
**Para que serve:** autenticar e abrir o espaço de trabalho.  
**Quem vê:** qualquer pessoa com usuário ativo; não há cadastro aberto nesta tela.  
**O que dá para fazer:** informar usuário e senha e entrar.  
**Como chegar:** abrir `/contas/login/` ou acessar uma página que exige login.

## Início — Minha mesa

**Menu:** `Início` · **título:** `Minha mesa`.  
**Para que serve:** reunir pendências, prazos, análise do cliente, atividade recente e atalhos do contrato selecionado.  
**Quem vê:** qualquer usuário autenticado. A lista considera as participações ativas; staff também pode consultar contratos sem participação.  
**O que dá para fazer:** trocar o contrato quando houver mais de um, abrir documentos e pendências, ir a importações disponíveis e consultar links de backup quando exibidos. As áreas “Mensagens / Integrações” e “Ações rápidas” só oferecem as opções que estiverem habilitadas.  
**Como chegar:** é a página aberta após o login; clique em `Início` no menu lateral para voltar.

A antecedência do aviso “Vence em N dias” vem do perfil do contrato e, por padrão, é de 3 dias.

## Painel

**Menu e título:** `Painel · [código interno]` e `Painel · [código interno]`.  
**Para que serve:** mostrar o avanço do contrato conforme o perfil vigente, com situações, recortes e indicadores configurados.  
**Quem vê:** participantes ativos do contrato entram autenticados. Quem não participa pode acessar a versão de acompanhamento com o PIN configurado para o contrato; o PIN também permite acesso sem login.  
**O que dá para fazer:** filtrar e agrupar os dados, abrir `Resumo executivo`, consultar `Fotos` e, para staff ou Administrador do contrato, ver o atalho para `Linhas recusadas` quando houver linhas abertas. `Guardar foto de hoje` aparece para staff ou Administrador do contrato.  
**Como chegar:** clique no painel do contrato na área de contratos da `Minha mesa` ou no menu lateral.

## Pendências e ações

### Pendências

**Menu e título:** `Pendências` · `Pendências`.  
**Para que serve:** centralizar itens que pedem acompanhamento, como erros, prazos, cronograma e linhas recusadas.  
**Quem vê:** staff e usuários com participação ativa no contrato; os dados seguem o contrato selecionado.  
**O que dá para fazer:** abrir os detalhes de cada grupo e do documento relacionado. Para itens que oferecem ação, registrar `Ignorar`, `Pedir correção ao cliente` ou `Já corrigi`; uma pendência ignorada pode ser reativada. Algumas opções dependem do tipo de item e do acesso.  
**Como chegar:** menu lateral `Pendências`, ou pelos atalhos e cartões na `Minha mesa`.

O grupo `Título diferente do ID` mostra o título atual do documento e o título do índice vigente. Quem pode editar títulos pode usar o título do ID; `Manter o atual` registra um motivo e oculta a pendência até que ela seja reativada.

### Pendências abertas

**Título:** `Pendências abertas`.  
**Para que serve:** consultar os itens que ainda estão em aberto e agrupá-los por categoria.  
**Quem vê:** staff e participantes ativos do contrato.  
**O que dá para fazer:** abrir cada categoria para ver os documentos e pendências correspondentes.  
**Como chegar:** em `Pendências`, use `Ver todos` no grupo desejado.

### Atrasados

**Título:** `Atrasados`.  
**Para que serve:** acompanhar prazos vencidos de análise e de revisões.  
**Quem vê:** staff e participantes ativos do contrato.  
**O que dá para fazer:** abrir os documentos listados e conferir vencimento, situação e tempo de atraso.  
**Como chegar:** abra o grupo `Atraso por faixa` na `Minha mesa` ou a opção `Atrasados` em Pendências.

### Pendências ignoradas

**Título:** `Pendências ignoradas`.  
**Para que serve:** rever itens que foram ignorados.  
**Quem vê:** staff e participantes ativos do contrato.  
**O que dá para fazer:** consultar o motivo e usar `Reativar pendência` para voltar a acompanhar um item.  
**Como chegar:** em `Pendências`, clique em `Ver todos › ignorados`.

## Documentos

**Menu e título:** `Documentos` · `Documentos`.  
**Para que serve:** localizar documentos do contrato e acompanhar sua situação vigente.  
**Quem vê:** staff e participantes ativos do contrato, qualquer que seja o papel; alterações restritas são liberadas conforme o papel.  
**O que dá para fazer:** buscar por código ou título, filtrar por categoria ou situação e abrir a pasta do documento. Staff e Administrador do contrato podem cancelar ou reativar documentos quando a ação estiver disponível.  
**Como chegar:** menu lateral `Documentos`; clique no código de uma linha para abrir a pasta.

### Pasta do documento

**Título:** o código do documento. A página tem as seções `Partes do código`, `Linha do tempo das emissões` e `Ações e Atividade`.  
**Para que serve:** reunir dados do documento, emissões, análises e histórico de ações.  
**Quem vê:** staff e participantes ativos do contrato.  
**O que dá para fazer:** consultar as partes do código e a linha do tempo; abrir `Editar título`; registrar motivo da reabertura quando permitido; e, para staff ou Administrador do contrato, cancelar ou reativar o documento quando aplicável.  
**Como chegar:** clique no código em `Documentos`, `Lista Mestra`, `Pendências` ou em uma linha de atividade.

### Editar título

**Título:** `Editar título · [código interno]` · cabeçalho `Editar título`.  
**Para que serve:** corrigir o título cadastrado do documento.  
**Quem vê:** staff ou Administrador do contrato.  
**O que dá para fazer:** informar o novo título e o motivo da alteração e salvar.  
**Como chegar:** na pasta do documento, clique em `Editar título`.

## Lista Mestra

**Menu e título:** `Lista Mestra` · `Lista Mestra`.  
**Para que serve:** consultar as emissões dos documentos em uma tabela.  
**Quem vê:** staff e participantes ativos do contrato.  
**O que dá para fazer:** buscar código ou título; filtrar por tipo, disciplina, fase e situação; exibir documentos cancelados; e abrir a pasta pelo código. A tabela mostra revisão, versão, datas, rótulo cronológico e situação da análise, conforme os dados disponíveis.  
**Como chegar:** menu lateral `Lista Mestra`.

## Contratos

### Lista de contratos

**Menu e título:** `Contratos` · `Contratos`.  
**Para que serve:** consultar os contratos cadastrados e seus perfis vigentes, participações e indicadores gerais.  
**Quem vê:** staff.  
**O que dá para fazer:** abrir o painel, a Lista Mestra ou os detalhes do contrato; usar `Editar no admin` para abrir o cadastro administrativo.  
**Como chegar:** menu lateral `Contratos`.

### Detalhe do contrato

**Título:** `[nome do contrato] · Contratos` · seção `Participantes`.  
**Para que serve:** ver o estado do contrato e as participações ativas por usuário e papel.  
**Quem vê:** staff.  
**O que dá para fazer:** consultar participantes e seguir para `Editar no admin`.  
**Como chegar:** clique em um contrato na lista `Contratos`.

## Importações

### Importar ID

**Menu:** `Importar ID` · **título:** `Importar Índice de Documentos`.  
**Para que serve:** cadastrar ou atualizar o índice previsto para um contrato. O formato é identificado pelos cabeçalhos e os códigos são interpretados pelo perfil vigente.  
**Quem vê:** staff.  
**O que dá para fazer:** selecionar arquivo e contrato, escolher os campos disponíveis, gerar uma prévia e confirmar a aplicação. A página também mostra índices recentes e links para linhas recusadas.  
**Como chegar:** menu lateral `Importar ID`.

### Importar situação PW

**Menu:** `Importar situação PW` · **título:** `Importar situação do PW`.  
**Para que serve:** importar uma extração de situação para reconstruir emissões e análises.  
**Quem vê:** staff.  
**O que dá para fazer:** selecionar o arquivo, contrato e data da extração; gerar uma prévia; conferir os estados explícitos e inferidos; confirmar; e consultar importações recentes.  
**Como chegar:** menu lateral `Importar situação PW` ou o atalho de importação na `Minha mesa`.

### Atualizar situação (planilha)

**Menu:** `Atualizar situação (planilha)` · **título:** `Importar situação por planilha padrão`.  
**Para que serve:** aplicar situação documental por uma planilha padrão, inclusive para fontes sem PW.  
**Quem vê:** staff ou participantes ativos com papel de Administrador do contrato ou Equipe técnica.  
**O que dá para fazer:** baixar o modelo, selecionar arquivo e contrato, gerar uma prévia e confirmar a aplicação; a página lista planilhas aplicadas recentemente.  
**Como chegar:** menu lateral quando permitido ou pelo link `Importar situação por planilha padrão` na tela `Importar Índice de Documentos`.

### Importar cronograma

**Menu e título:** `Importar cronograma` · `Importar cronograma`.  
**Para que serve:** registrar previsões de emissão dos documentos.  
**Quem vê:** staff.  
**O que dá para fazer:** selecionar arquivo e contrato, gerar prévia, conferir linhas aceitas ou recusadas e confirmar; também consultar importações recentes.  
**Como chegar:** menu lateral `Importar cronograma`.

### Linhas recusadas

**Título:** `Linhas recusadas`.  
**Para que serve:** consultar linhas de ID ou situação que não foram aplicadas.  
**Quem vê:** staff e qualquer participante ativo do contrato. Apenas staff ou Administrador do contrato pode reprocessar linhas.  
**O que dá para fazer:** consultar código e motivo; gerar uma prévia de reprocessamento pelo perfil vigente; confirmar; e conferir quais linhas foram aceitas ou continuam recusadas.  
**Como chegar:** pelo aviso no `Painel`, pelo link na tela de importação de ID ou por um evento em `Atividade`.

### Histórico de importações

**Para que serve:** consultar os lotes de ID, situação do PW ou por planilha padrão e cronograma já aplicados ao contrato, com data, responsável, arquivo e resumo.
**Quem vê:** staff e qualquer participante ativo do contrato; a tela é somente para consulta. Acesse pelo link nas telas de importação ou em `Linhas recusadas`.

## Atividade

**Menu e título:** `Atividade` · `Atividade`.  
**Para que serve:** consultar eventos registrados no contrato.  
**Quem vê:** staff ou Administrador do contrato ativo.  
**O que dá para fazer:** filtrar por contrato, pessoa, ação, período ou código; baixar os eventos filtrados em `Baixar planilha (CSV)`; abrir detalhes do evento; seguir para o documento ou para as linhas recusadas; e navegar pelas páginas de resultados.  
**Como chegar:** menu lateral `Atividade` quando o acesso está disponível; na `Minha mesa`, use `Ver toda a atividade` se o link aparecer.

## Resumo executivo

**Título:** `Resumo executivo · [código interno]`.  
**Para que serve:** apresentar pendências e avanço do contrato em formato compacto.  
**Quem vê:** usuário autenticado com participação ativa no contrato. O PIN público do Painel não libera esta tela.  
**O que dá para fazer:** consultar a lista de pendências e os recortes de avanço e usar `Imprimir / salvar PDF`.  
**Como chegar:** no `Painel` do contrato, clique em `Resumo executivo`.

## Fotos do contrato

**Menu/título da tela:** não há item lateral; a tela tem o cabeçalho `Fotos do contrato`.  
**Para que serve:** consultar fotos de acompanhamento guardadas para o contrato.  
**Quem vê:** usuário autenticado com participação ativa no contrato.  
**O que dá para fazer:** consultar data e autor da foto; staff ou Administrador do contrato também pode usar `Guardar foto de hoje` no Painel.  
**Como chegar:** no `Painel`, clique em `Fotos`; use `Voltar ao Painel` para retornar.

## Backups do sistema

**Título:** `Backups do sistema`. Não há item de backup no menu lateral.  
**Para que serve:** consultar cópias de segurança do banco SQLite e os registros de sucesso ou falha.  
**Quem vê:** staff e superusuário. Preparar uma restauração é reservado ao superusuário.  
**O que dá para fazer:** consultar data, arquivo, tamanho e registro; staff com acesso de superusuário pode preparar uma restauração, conferir a confirmação de data e receber o comando a executar. A restauração não é acionada diretamente pela tela.  
**Como chegar:** use `Ver backups` ou `Ver histórico de backups` na `Minha mesa` quando o link for exibido. O endereço da lista é `/backups/`.

## Admin — perfil do contrato

**Menu:** `Admin` · no Django Admin, o cadastro aparece como `Perfil do contrato`.  
**Para que serve:** configurar como o sistema interpreta e organiza os documentos daquele contrato: caixas e separadores do código, valores válidos, regras documentais e vigência do perfil.  
**Quem vê:** staff com as permissões correspondentes do Django Admin. A administração do perfil é uma tarefa de configuração; papel de contrato, isoladamente, não concede acesso ao Admin.  
**O que dá para fazer:** criar ou editar a versão do perfil; consultar `Caixas do código`, `Separadores` e `Exemplo de código`; usar `Testar códigos` e abrir `Feriados`. O cadastro de Contrato também reúne perfis e escopos; as participações ligam usuários a contratos e papéis.  
**Como chegar:** clique em `Admin` no menu lateral. Para um contrato específico, abra `Contratos` → `Editar no admin`; no cadastro do contrato, abra ou adicione o `Perfil do contrato` associado.

## GRDs

### Lista de GRDs

**Menu e título:** `GRDs` · `GRDs`.  
**Para que serve:** consultar as guias de remessa registradas para o contrato selecionado.  
**Quem vê:** staff e participantes ativos do contrato.  
**O que dá para fazer:** consultar data, destinatário e quantidade de documentos; abrir uma GRD; e, para staff, Administrador do contrato ou Equipe técnica, iniciar uma nova remessa.  
**Como chegar:** menu lateral `GRDs`.

### Nova GRD

**Título:** `Nova GRD`.  
**Para que serve:** registrar no sistema uma remessa de documentos do contrato.  
**Quem vê:** staff, Administrador do contrato ou Equipe técnica com participação ativa no contrato.  
**O que dá para fazer:** informar data, destinatário e observação; colar um código por linha; conferir os documentos aceitos e recusados na `Prévia`; e confirmar a criação. Cada código aceito inclui a última emissão do documento.  
**Como chegar:** em `GRDs`, clique em `Nova GRD`.

### Detalhe da GRD

**Título:** `[rótulo da GRD]`.  
**Para que serve:** consultar e imprimir os dados e documentos incluídos na remessa.  
**Quem vê:** staff e participantes ativos do contrato.  
**O que dá para fazer:** consultar rótulo, data, destinatário, observação, autor e itens; abrir a pasta de um documento; e usar `Imprimir` para imprimir ou salvar em PDF pelo navegador.  
**Como chegar:** clique no rótulo de uma GRD na lista ou em um link de GRD na linha do tempo da pasta do documento.

## Primeiros passos

1. Crie a primeira conta administrativa com `createsuperuser` seguindo os comandos de desenvolvimento em [plataforma/README.md](../plataforma/README.md).
2. Entre no Django Admin, crie os usuários da equipe e marque como staff quem precisa administrar a plataforma. Em `Participação`, associe cada usuário ao contrato e ao papel correspondente.
3. No Django Admin, crie um registro em `Contratos`. Abra esse cadastro, adicione um `Perfil do contrato` ativo e informe início de vigência e definição compatível com o padrão documental do contrato.
4. Abra `Importar ID`, escolha o contrato e o arquivo do índice, revise a prévia e confirme a importação.
5. Abra `Importar situação PW`, escolha o contrato e a data da extração, revise a prévia e confirme. Consulte `Linhas recusadas` para tratar as linhas que não forem aplicadas.
6. Acesse `Painel · [código interno]` pela `Minha mesa` ou pelo menu lateral e confira o avanço calculado a partir do perfil e dos dados importados.
