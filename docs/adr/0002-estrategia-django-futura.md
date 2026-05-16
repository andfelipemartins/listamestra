# ADR 0002: Estrategia Django Futura

Data: 2026-05-16

Status: Proposta

## Contexto

O SCLME pode evoluir de MVP Streamlit para um produto interno mais robusto. Uma das stacks candidatas para esse futuro e Django com PostgreSQL.

Django e um candidato forte porque oferece:

- ORM;
- migrations;
- autenticacao;
- admin;
- permissoes;
- estrutura madura para CRUD;
- ecossistema consolidado;
- boa integracao com PostgreSQL;
- base adequada para aplicacoes corporativas internas.

## Decisao

Django sera considerado uma opcao forte para versao corporativa futura.

Nao migrar agora.

## Motivos Para Nao Migrar Agora

- O fluxo documental ainda esta em consolidacao.
- Existem dividas arquiteturais a reduzir antes da migracao.
- O `core` ainda conhece SQLite diretamente.
- As paginas ainda possuem SQL e regra de aplicacao.
- Services e repositories ainda nao existem formalmente.
- Uma migracao agora misturaria reescrita tecnica com descoberta de produto.

## Criterios Para Considerar Migracao

Considerar Django quando:

- o fluxo documental estiver estabilizado;
- services/repositories estiverem criados;
- `core` estiver independente do Streamlit;
- autenticacao real for necessaria;
- multiplos usuarios simultaneos forem requisito real;
- PostgreSQL for necessario;
- admin, permissoes e auditoria robusta forem exigidos;
- CRUD operacional superar o conforto do Streamlit;
- o uso deixar de ser demo/piloto e virar operacao corporativa.

## Caminho Provavel

1. MVP Streamlit.
2. Consolidacao arquitetural.
3. Criacao de services e repositories.
4. Extracao de dominio.
5. Reducao da dependencia de DataFrame como contrato interno.
6. Separacao de auth puro e auth UI.
7. Avaliacao de Django.
8. Possivel Django + PostgreSQL + HTMX/templates.

## Possivel Stack Futura

- Django;
- PostgreSQL;
- Django templates;
- HTMX para interacoes dinamicas;
- Celery/RQ apenas se houver necessidade real de tarefas assicronas;
- armazenamento externo para arquivos, se necessario;
- autenticacao corporativa se exigida.

## Consequencias

### Positivas

- Reduz risco de migracao prematura.
- Permite preservar regras ja validadas.
- Prepara o projeto para uma migracao menos traumática.
- Mantem foco atual em confiabilidade do dominio.

### Negativas

- A stack atual continua com limitacoes.
- Algumas features corporativas terao que esperar.
- A refatoracao intermediaria exige disciplina antes de novas funcionalidades grandes.

