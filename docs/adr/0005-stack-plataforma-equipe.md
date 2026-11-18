# ADR 0005: Stack da plataforma da equipe

Data: 2026-11-18

Status: **Proposta. Aguarda a decisão do dono** (D-007)

Substitui, se aprovada: ADR 0001 (stack atual) como destino. A ADR 0002 deixa de ser "futura".

## Contexto

As decisões de 2026-11-18 mudaram o que o produto precisa ser:

| Decisão | Exigência técnica |
|---------|-------------------|
| D-003 · ferramenta da equipe/empresa | Multiusuário simultâneo, login real, deploy fora do PC do dono |
| D-005/D-008 · perfil de contrato configurável | Telas de administração com muitos formulários (estrutura do código, valores válidos, máquina de revisão) |
| D-006 · perfis (admin, equipe, projetista, chefia) | Permissões por perfil e por contrato, atribuição de tarefas |
| D-015 · painel com PIN de leitura | Página pública com controle de acesso simples |
| D-016 · portal do projetista | Formulário externo de entrega com upload de arquivo |
| D-017 · arquivos em etapas | Armazenamento de arquivos com caminho de crescimento |
| D-006 · tudo auditável | Histórico de alterações de cada registro |

O que existe hoje (medido nesta data):

- `core/` tem cerca de 7.700 linhas de Python, com regra de negócio em engine/services/repositories.
  Só `core/auth/permissions.py` importa Streamlit. **17 módulos de `core/` falam SQLite
  direto** (`get_connection`/SQL escrito à mão), incluindo engine e importers, e não só os
  repositories.
- `pages/` tem cerca de 2.100 linhas de Streamlit. `api/` tem um adapter FastAPI de 160 linhas.
- `tests/` tem cerca de 10.400 linhas, quase todos testes de `core/` com SQLite em `tmp_path`.

## Opções

### A. Manter Streamlit + SQLite e adicionar o que falta

- **A favor:** zero reescrita e valor imediato. A Lista Mestra definitiva sai mais rápido.
- **Contra:** o Streamlit não foi feito para multiusuário com login, formulários externos
  e páginas públicas. Cada clique reexecuta a página inteira, e o estado por usuário é frágil.
  O SQLite com escrita concorrente de uma equipe tem limite real. O login teria de ser feito
  à mão (o dono já disse que o login atual "estava um lixo", C1). O portal do projetista e o
  painel com PIN viram gambiarras ou dependem de um segundo app (FastAPI), e então já são duas
  stacks.

### B. Django + PostgreSQL (com HTMX para interatividade)

- **A favor:** login, sessões, permissões, admin, migrations, formulários e upload já vêm prontos.
  O **Django Admin resolve grande parte da tela de configuração do perfil de contrato quase
  de graça**, e é exatamente o "cerne do produto" (D-008). O PostgreSQL aguenta a equipe e
  tem JSONB, útil para guardar o perfil configurável. Auditoria fica simples com
  django-simple-history. O deploy é bem conhecido (um servidor, Docker).
- **Contra:** é reescrita da interface (2.100 linhas de páginas) e da camada de dados (os 17
  módulos que fazem SQL direto passam para o ORM). Gráficos e dashboards dão mais trabalho que
  no Streamlit (é preciso Plotly ou Chart.js no template).

### C. FastAPI + front-end SPA (React/Vue) + PostgreSQL

- **A favor:** máxima flexibilidade de interface e aproveita o adapter `api/` existente.
- **Contra:** são duas bases de código e duas stacks para uma pessoa e uma esteira manterem.
  Login, permissões, admin e formulários precisam ser feitos à mão. É o caminho mais caro.

## Recomendação

**Opção B: Django + PostgreSQL + HTMX**, com migração incremental, e não um big bang:

1. **Agora:** o Marco 11 (Central de Pendências) termina no Streamlit, porque já está quase
   pronto. Regra nova continua indo para `core/` sem Streamlit.
2. **Marco de fundação Django (próximo grande Marco):** projeto Django no mesmo repositório, com
   modelos para contrato, perfil de contrato, documento, revisão, GRD e usuário/perfil.
   Login real e admin. Os engines puros de `core/` (status, ciclo de vida, emissão inicial,
   pendências) são reaproveitados. O que faz SQL direto passa a receber dados ou um repository.
3. **Lista Mestra definitiva (D-010) já nasce em Django**, com o perfil de contrato configurável
   (D-008) desde o primeiro dia. Fazer a Lista Mestra "definitiva" no Streamlit seria fazê-la
   duas vezes.
4. O Streamlit continua rodando em paralelo como ferramenta pessoal até a paridade, e depois é
   aposentado.

**Por quê:** os três requisitos mais novos e mais importantes (multiusuário, perfil
configurável por admin e projetista externo) são justamente o que o Django resolve de fábrica
e o que o Streamlit faz mal. O custo da reescrita é limitado (a interface é a menor parte do
código), e a esteira com Codex reduz esse custo. Adiar só aumenta o volume que depois teria
de ser reescrito.

**Riscos e mitigação:**

- Reescrita parar no meio → migração por Marco, com o Streamlit funcionando até a paridade.
- Deploy e infra da empresa (B2: não depender de bênção de TI) → primeiro deploy num servidor
  próprio barato ou no próprio PC com Docker. A empresa entra quando o produto estiver
  irresistível.
- Dashboards → Plotly já é dependência e funciona dentro de templates Django.

## Decisão

_Pendente._ O dono escolhe no Control Room: B (recomendada), A ou C.

## Consequências se B for aprovada

- A ADR 0001 passa a descrever o legado. A ADR 0002 vira "aceita".
- O roadmap ganha o Marco "Fundação Django". O perfil de contrato configurável e a Lista
  Mestra definitiva entram depois dele.
- A ADR 0004 (recebimento de GRD por FastAPI) é reavaliada: o recebimento vira uma view Django.
