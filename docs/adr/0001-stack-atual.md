# ADR 0001: Stack Atual do SCLME

Data: 2026-05-16

Status: Aceita

## Contexto

O SCLME ja possui um MVP funcional para controle documental de engenharia. A stack atual e Python, Streamlit e SQLite, com Pandas, OpenPyXL, Plotly e Pytest.

O sistema ja cobre fluxos reais:

- home de contratos;
- dashboard;
- importacoes;
- comparacao ID x Lista;
- cadastro manual;
- consulta documental;
- parsers;
- importadores;
- engines;
- exportadores;
- permissoes basicas;
- banco SQLite;
- testes.

A analise arquitetural identificou riscos para crescimento futuro, mas tambem confirmou que a stack atual ainda e adequada para consolidacao do MVP.

## Decisao

Manter Streamlit + SQLite durante a fase MVP e pre-produto.

Nao migrar para Django neste momento.

## Motivos

- velocidade de desenvolvimento;
- facilidade de teste;
- foco em validar o dominio documental;
- menor curva de aprendizado;
- app local funcional;
- baixo custo operacional;
- capacidade de demonstracao rapida;
- regras centrais ja implementadas e testadas.

## Consequencias Positivas

- O projeto continua evoluindo sem interrupcao por migracao.
- O MVP pode ser consolidado antes de uma reescrita.
- A equipe mantem foco em regra de negocio e confiabilidade.
- O custo tecnico imediato permanece controlado.

## Consequencias Negativas

- Limitacoes para multiusuario.
- Autenticacao real limitada.
- Interface menos flexivel que um frontend dedicado.
- Deploy corporativo mais restrito.
- CRUD complexo pode ficar dificil de manter.
- SQLite nao resolve concorrencia robusta.

## Diretriz

Nao adicionar features grandes sem reduzir acoplamento estrutural.

Antes de retomar grandes marcos funcionais, o projeto deve:

- remover SQL direto das paginas;
- criar repositories;
- criar services;
- reduzir dependencia de Streamlit fora da UI;
- preservar `core/` como base independente;
- manter testes para regras centrais.

## Criterios Para Reavaliar

Reavaliar esta decisao se:

- multiplos usuarios precisarem gravar simultaneamente;
- autenticacao corporativa for obrigatoria;
- PostgreSQL se tornar necessario;
- auditoria formal for exigida;
- CRUD operacional crescer alem do confortavel em Streamlit;
- TI exigir deploy corporativo padronizado.

