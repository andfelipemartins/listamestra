# Visao de Produto do SCLME

Marco 10.6 - Consolidacao Arquitetural Pre-Produto — Concluido.

Data de conclusao: 2026-05-16

## O Que E o SCLME

O SCLME - Sistema de Controle de Lista Mestra de Projetos Executivos - e um sistema para controle documental de engenharia. Ele nasceu como alternativa a uma Lista Mestra mantida em Excel e hoje opera como um MVP funcional em Python, Streamlit e SQLite.

O sistema concentra informacoes de documentos previstos, documentos emitidos, revisoes, arquivos, status, comparacoes entre Indice de Documentos e Lista de Documentos, dashboards e exportacoes.

## Problema Que Resolve

Em contratos de engenharia, o controle documental costuma depender de planilhas, relatorios recebidos de terceiros, arquivos em pastas, validacoes manuais e conhecimento contextual de quem opera o processo.

Esse modelo gera riscos:

- divergencia entre documentos previstos e documentos emitidos;
- dificuldade para saber o progresso real do contrato;
- perda de historico de revisoes;
- baixa rastreabilidade de inconsistencias;
- dificuldade para explicar status em reunioes;
- retrabalho na conferencia manual;
- dependencia excessiva de pessoas especificas.

O SCLME organiza essas informacoes em uma base rastreavel, com regras documentadas e testaveis.

## Publico-Alvo Inicial

O publico-alvo inicial e formado por equipes envolvidas no controle documental de contratos de engenharia:

- construtoras;
- equipes de controle documental;
- equipes de engenharia;
- projetistas;
- equipes de contrato;
- coordenadores que precisam acompanhar progresso documental;
- responsaveis por listas mestras, GRDs, revisoes e status.

## Primeiro Caso de Uso

O primeiro caso de uso e a Linha 15 / Ragueb.

Esse caso validou o produto com dados reais, incluindo:

- Lista de Documentos;
- Indice de Documentos;
- revisoes;
- aprovacao historica;
- status atual;
- comparacao ID x Lista;
- busca documental;
- exportacoes;
- controle basico de arquivos.

## Estado Atual do Produto

O SCLME ja possui:

- home com contratos;
- dashboard;
- importacao da Lista de Documentos;
- importacao do Indice de Documentos;
- importacao de arquivos via `nomes.txt`;
- comparacao ID x Lista;
- cadastro manual;
- consulta documental;
- parsers de codigo e arquivo;
- importadores;
- engines de status, comparacao, preview de arquivos e emissao inicial;
- exportadores Excel;
- permissoes basicas;
- banco SQLite;
- repositories: `ContractRepository`, `ImportacaoRepository`, `DocumentoRepository`, `RevisaoRepository`;
- services: `ContractService`, `ImportacaoService`, `DocumentoService`, `CadastroService`, `DashboardService`;
- testes automatizados (570 testes).

## MVP Tecnico, Produto Interno e SaaS Futuro

### MVP Tecnico

O MVP tecnico prova que o dominio pode ser automatizado. Ele prioriza leitura correta das fontes atuais, calculos coerentes, rastreabilidade, busca e exportacao.

Caracteristicas:

- stack simples;
- deploy simples;
- baixo custo operacional;
- foco em validar regra documental;
- uso controlado;
- pouca preocupacao com multiusuario robusto.

### Produto Interno

Um produto interno exige mais confiabilidade operacional, padronizacao de fluxos e suporte a mais usuarios.

Caracteristicas esperadas:

- regras mais bem isoladas da interface;
- camada de services e repositories;
- banco mais controlado;
- auditoria mais clara;
- autenticacao real ou integrada;
- permissao mais robusta;
- deploy previsivel.

### Produto SaaS Futuro

Um SaaS exigiria uma arquitetura mais ampla, preparada para multiplos clientes, contratos, usuarios e ambientes.

Caracteristicas esperadas:

- multi-tenant;
- banco gerenciado;
- autenticacao e autorizacao robustas;
- auditoria completa;
- isolamento de dados por cliente;
- controle de plano/acesso;
- observabilidade;
- suporte operacional;
- politica clara de backup e retencao.

O SCLME atual ainda nao esta nessa fase.

## Fora do Escopo Imediato

Nao faz parte do escopo imediato:

- migrar para Django;
- migrar para React/Next;
- implementar SaaS;
- substituir GED/ProjectWise;
- integrar API corporativa;
- implementar autenticacao corporativa;
- resolver multiusuario concorrente;
- criar workflow formal de aprovacao;
- fazer CRUD completo de todos os dados;
- criar auditoria empresarial completa;
- trocar SQLite por PostgreSQL neste momento.

## Direcao do Produto

A direcao atual e retomar os marcos funcionais (Marco 11 em diante) com a consolidacao arquitetural concluida.

## Resultado do Marco 10.6

O Marco 10.6 foi bem sucedido. Criterios atingidos:

- estado atual da arquitetura documentado (`docs/ARCHITECTURE.md`);
- riscos tecnicos conhecidos e registrados;
- estrategia de nao migrar agora registrada (`docs/adr/0001-stack-atual.md`);
- futura possibilidade de Django documentada (`docs/adr/0002-estrategia-django-futura.md`);
- criacao de services/repositories definida e implementada (`docs/adr/0003-camada-services-repositories.md`);
- roadmap atualizado com Marco 10.6 concluido antes do Marco 11;
- suite de testes com 570 testes passando.

