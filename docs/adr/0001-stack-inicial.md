# ADR 0001: Stack Inicial do SCLME

Data: 2026-05-16

Status: Aceita

## Contexto

O SCLME nasceu como uma ferramenta para validar e operacionalizar o controle documental de engenharia a partir de fontes reais, especialmente Lista de Documentos, Indice de Documentos, arquivos locais/SharePoint e controles historicos em Excel.

A prioridade inicial foi provar valor rapidamente:

- importar dados reais;
- interpretar codigos documentais;
- calcular status e aprovacao historica;
- comparar previsto x emitido;
- gerar dashboard;
- permitir consulta por documento;
- exportar relatorios;
- testar regras centrais.

## Decisao

Manter a stack inicial:

- Streamlit para interface;
- SQLite para persistencia local;
- Pandas para processamento tabular;
- OpenPyXL para Excel;
- Plotly para graficos;
- Pytest para testes.

Nao migrar a stack neste momento.

## Justificativa

Streamlit permite evolucao rapida da interface e facilita demonstracao para usuarios internos. SQLite reduz complexidade de instalacao e deploy local. Pandas e OpenPyXL sao adequados para o dominio atual, que depende fortemente de planilhas. Plotly atende aos dashboards. Pytest permite proteger regras de negocio conforme o sistema cresce.

A stack atual e suficiente para consolidar uma versao piloto, validar regras e organizar o produto.

## Limitacoes Aceitas

Esta decisao aceita as seguintes limitacoes:

- multiusuario limitado;
- autenticacao nao corporativa;
- permissoes internas sem seguranca empresarial completa;
- concorrencia limitada por SQLite;
- deploy corporativo ainda indefinido;
- CRUD complexo pode ficar desconfortavel em Streamlit;
- Streamlit Community Cloud serve para demo, nao como arquitetura definitiva.

## Diretrizes Enquanto Esta Stack For Mantida

- Paginas Streamlit nao devem concentrar regra de negocio.
- `core/` deve permanecer independente da interface.
- Acesso ao banco deve passar por camada propria.
- Testes devem priorizar parsers, importadores, engine e exportadores.
- Novas regras devem ser escritas como funcoes testaveis antes de serem exibidas na UI.
- Decisoes de produto devem ser registradas quando alterarem arquitetura, dados ou fluxo operacional.

## Alternativas Consideradas

### Django + PostgreSQL

Adequado para produto interno robusto, multiusuario, com autenticacao, CRUD, auditoria e banco centralizado.

### Django + HTMX

Boa alternativa para manter Python no backend e criar uma interface web mais estruturada sem adotar um frontend pesado.

### FastAPI + React/Next

Separacao clara entre API e frontend, maior flexibilidade visual e de produto, mas com custo maior de desenvolvimento e operacao.

### Power Platform

Pode complementar fluxos corporativos, formularios, SharePoint, Outlook e automacoes. Nao substitui necessariamente o motor de regras do SCLME.

## Consequencias

### Positivas

- Mantem velocidade de desenvolvimento.
- Evita migracao prematura.
- Preserva investimento nos testes e regras ja construidas.
- Permite apresentar e validar o produto rapidamente.
- Mantem baixa complexidade operacional no curto prazo.

### Negativas

- Nao resolve multiusuario corporativo.
- Nao resolve autenticacao real.
- Nao resolve concorrencia robusta.
- Pode exigir migracao futura caso o uso cresca.
- Pode limitar UX em fluxos CRUD mais complexos.

## Criterios Para Reavaliar

Reavaliar esta decisao quando ocorrer um ou mais destes sinais:

- necessidade real de varios usuarios gravando simultaneamente;
- exigencia de autenticacao corporativa;
- necessidade de auditoria formal;
- banco SQLite se tornar gargalo;
- fluxo de edicao/CRUD ficar grande demais para Streamlit;
- demanda por deploy corporativo com suporte de TI;
- necessidade de API para integracoes externas.

