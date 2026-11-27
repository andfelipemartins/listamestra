# Roadmap do SCLME

Data: 2026-11-27

Este arquivo é a fonte única do roadmap no repositório; o status muda primeiro no painel do dono (Control Room). O Streamlit (main.py, pages/) é legado; a Plataforma Django (plataforma/) é o produto (D-020, D-121).

## Marcos

| Marco | Objetivo | Status | Blocks · hash |
| --- | --- | --- | --- |
| m00 · Base do produto (Marcos 0–10.6) | Entregar a base documental: parser, importações, banco, painéis, cadastro, status, relatórios e camadas de serviço. | Concluído | — |
| m01 · Revisão do Cadastro Manual (10.7) | Cadastrar documentos colando códigos e revisar a experiência do fluxo. | Pausado | 10.7.1–10.7.4; 10.7.5; 10.7.6 |
| m02 · Central de Pendências (11) | Reunir o que exige ação para resolver ou ignorar pendências do contrato (J1). | Concluído | 009; 011; 013 |
| m03 · GRDs (14) | Criar e consultar GRDs na Plataforma Django (D-105, D-110, D-122). | Em andamento | 001; 002; 003; 007; 008; 074:8578d59 |
| m04 · Infraestrutura e governança | Manter operáveis a infraestrutura e a esteira de trabalho do projeto. | Concluído | 004; 005; 006; 010; 012 |
| m05 · Reavaliar com a nova visão (12–20) | Reavaliar e ampliar as primeiras fatias de edição, conciliação, GED/PW, relatórios, snapshots, contratos, auditoria e apresentação. | Em andamento | 069:50cf166; 070:3002707; 071:3e94684; 072:7bb35dd; 073:b956b73; 075:3726e0f; 076:f4ba360 |
| m06 · Lista Mestra definitiva | Substituir de vez a planilha com macro pela tela da Lista Mestra (D-010). | Em andamento | 068:c618840 |
| m07 · Fundação Django | Estabelecer login, perfis, modelos e configuração documental por contrato. | Concluído | 014:122786d; 015:c0ab378; 016:8224d08; 017:7298eae; 016c:0d09f55 |
| m08 · Dados reais e painel da chefia | Importar dados reais do ID e do PW e apresentar o acompanhamento da chefia. | Em avaliação | 018:56572ec; 020a:2c75bef; 016d:168d2a0; 019:a2d9051; 020b:40c205b; 020c:3f65c00; 021:891e6b6; 022:5ac5a49; 023:046d799; 024:bbafe78; 025:9d1cc91; 026:3864ef7; t30 |
| m09 · Tela de ação e pendências | Dar controle por login e contrato (D-042) para prazos, pendências e ações. | Em andamento | 047:7136dee; 048:5cbacac; 049:0059ee8; 057:7f83f4a; 058:5708b33; 059:621571f; 060:e785c28; 061:7f89a28; 062:2a58e6f; 063:039ad93; 064:e0210cc; 065:5bbe677; 066:ea106a1; 067/067b:b6f5de1 |

## O que falta e do que depende

- **m03 · GRDs:** a primeira fatia (block-074) aguarda avaliação (AU1, AT2). Depois: cópias por formato; distribuição por setor (AN2); GRD antiga como histórico (AN6).
- **m05 · Reavaliar com a nova visão:** próximo passo é reavaliar os Marcos 12–20. O arquivo associa as fatias entregues a Marco 12 (D-117, AP1), 13 (D-123, AU2, AV1), 16 (D-118, AQ1), 17 (D-119, AR1), 18 (D-120, AS1), 19 (D-124, AV2) e 20 (D-121). Marco 15 já está coberto em boa parte pelos blocks 019 e 062.
- **m06 · Lista Mestra:** aguarda avaliação da primeira fatia (AO1) e a escolha da segunda fatia (AN2).
- **m08 · Dados reais e painel:** pronto para sua aprovação (Y1).
- **m09 · Tela de ação:** faltam GRD antiga como histórico (D-110, AN6), alerta de prazo no perfil (D-116, AN7), tarefas da equipe e card Minhas tarefas (D-112/D-115, AN3/AN4/AN8).

## Marcos antigos (era Streamlit)

- Marcos 0–10.6: m00; Marco 10.7: m01; Marco 11: m02; Marcos 12–13 e 15–20: m05; Marco 14: m03.
- O Marco 11, Central de Pendências, está concluído. Os Marcos 12–20 passaram para m05, com primeiras fatias entregues; o Marco 14 segue em m03.
- O Marco 10.6 preparou o crescimento: o MVP já tinha valor, mas SQL direto nas páginas e dependência de Streamlit/SQLite dificultavam evoluir.
- Também faltavam services/repositories, com riscos para multiusuário, autenticação e implantação corporativa. Foram documentadas arquitetura e visão de produto, criadas camadas de serviço/repositório e refatoradas três páginas; a suíte da época registrou 570 testes passando.
- Naquele marco, a migração para Django ainda não era o objetivo; a decisão posterior de construir a Plataforma Django está em D-020.