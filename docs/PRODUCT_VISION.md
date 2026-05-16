# Visao de Produto do SCLME

Checkpoint de produto em 2026-05-16.

## Problema

O controle da Lista Mestra de documentos de engenharia ainda depende fortemente de planilhas, verificacoes manuais e conhecimento contextual. Isso gera risco de divergencia, retrabalho, dificuldade de auditoria e pouca visibilidade consolidada sobre progresso, pendencias e status documental.

## Proposta

O SCLME deve ser uma ferramenta operacional para controlar documentos previstos, documentos emitidos, revisoes, aprovacoes historicas, arquivos vinculados, divergencias e indicadores de progresso.

O objetivo nao e apenas substituir uma planilha. O objetivo e transformar regras de controle documental em um sistema rastreavel, testavel e consultavel.

## Usuario Principal

Gestor de documentacao, engenheiro ou responsavel pelo controle da Lista Mestra em contrato de engenharia.

Esse usuario precisa:

- importar dados recebidos de planilhas e relatorios;
- comparar o previsto com o emitido;
- entender progresso por trecho, status e documento;
- pesquisar rapidamente um documento;
- explicar divergencias em reunioes;
- exportar evidencias e relatorios;
- reduzir dependencia de verificacao manual.

## Escopo Atual

O produto atual cobre:

- cadastro de contratos;
- importacao da Lista de Documentos;
- importacao do Indice de Documentos;
- importacao de lista de arquivos;
- parser de codigo documental;
- cadastro manual de documentos e revisoes;
- dashboard de progresso;
- comparacao ID x Lista;
- detalhe por documento;
- linha do tempo de revisoes;
- regras de status e aprovacao historica;
- exportacoes Excel;
- testes automatizados para regras centrais.

## O Que o Produto Deve Fazer Bem Agora

Nesta fase, o SCLME deve ser certeiro em:

- ler corretamente as fontes atuais;
- preservar historico de revisoes;
- calcular status atual sem ambiguidade;
- calcular aprovacao historica sem contar revisoes intermediarias como finais;
- comparar documentos previstos e emitidos;
- exibir divergencias com clareza;
- permitir busca rapida por documento;
- exportar dados coerentes com a tela;
- registrar inconsistencias de importacao;
- manter regras de negocio testadas.

## O Que Ainda Nao E Objetivo Principal

Ainda nao e objetivo desta fase:

- substituir GED/ProjectWise;
- operar como sistema corporativo multiusuario completo;
- ter autenticacao corporativa;
- ter workflow formal de aprovacao;
- ser fonte unica oficial do cliente;
- fazer CRUD complexo de todos os dados;
- ter API publica;
- migrar para outra stack.

## Principios de Produto

### Confiabilidade Antes de Volume

O app deve acertar poucos fluxos importantes antes de expandir para muitos fluxos superficiais.

### Regra Clara Antes de Interface Bonita

Visual importa, mas o valor central esta nas regras corretas de engenharia documental.

### Rastreabilidade Sempre

Importacoes, inconsistencias, revisoes e divergencias devem ser rastreaveis.

### Sem Magica Oculta

Sempre que o sistema calcular status, aprovacao ou divergencia, a regra deve ser explicavel.

### Excel Como Entrada, Nao Como Prisao

O produto pode continuar aceitando Excel como fonte, mas deve reduzir a dependencia de verificacao manual em Excel.

## Riscos de Produto

| Risco | Impacto | Mitigacao |
| --- | --- | --- |
| Regra de negocio mal entendida | Indicadores errados | Testes, validacao contra planilha manual e documentacao de regra |
| Dados inconsistentes de origem | Importacao ruidosa | Inconsistencias auditaveis e mensagens claras |
| Uso multiusuario prematuro | Perda de confianca | Manter piloto controlado ate definir arquitetura de producao |
| UI crescer demais em Streamlit | Manutencao dificil | Regras fora da UI e componentes/helpers testaveis |
| Deploy demo confundido com producao | Expectativa errada | Documentar limite do Streamlit Cloud/SQLite |

## Evolucao Possivel

### Curto Prazo

- consolidar versao piloto;
- limpar dados de demo;
- validar indicadores contra controle manual;
- melhorar mensagens e telas criticas;
- documentar regras principais.

### Medio Prazo

- central de pendencias;
- edicao operacional controlada;
- conciliacao assistida;
- importador de status GED/PW;
- relatorio executivo;
- snapshots mensais.

### Longo Prazo

- banco centralizado;
- autenticacao real;
- auditoria completa;
- multiusuario;
- integracao corporativa;
- possivel migracao para Django, Django + HTMX ou FastAPI + React/Next.

## Definicao de Sucesso da Versao Piloto

A versao piloto e bem sucedida se:

- os numeros principais batem com o controle manual validado;
- usuarios conseguem entender o dashboard sem explicacao longa;
- divergencias ID x Lista sao identificadas corretamente;
- documentos podem ser encontrados rapidamente;
- exportacoes apoiam reunioes e cobrancas;
- as regras centrais estao cobertas por testes;
- limitacoes de deploy e multiusuario estao claras.

