# Estudo: o que a planilha com macro faz (insumo para a Lista Mestra definitiva)

*2026-11-18 · base: D-022 · planilha `entrada/…Macro.xlsm` (fora do Git) e os módulos
`Mother`, `ColunaAC`, `ColunaN`, `ColunaO` e `ColunaX` anexados no Control Room*

Aqui só entra a **estrutura** da planilha. Nenhum dado real.

## Abas

| Aba | Papel | O que vira na plataforma |
|-----|-------|--------------------------|
| ID (data) | Escopo previsto: código desmontado em partes, título, status | Documentos previstos (já existe: `documentos_previstos`) |
| Lista de documentos (cerca de 2.200 linhas, 62 colunas) | **Uma linha por emissão** (código + revisão + versão), com blocos por setor | Documento + Emissões + eventos por setor |
| RESUMO | Tabela dinâmica por tipo e classe | Dashboard (D-010) |
| MO / MO1 | Tabelas de apoio (classe → módulo/título) | Vocabulário do perfil de contrato |
| Lista de Croquis | Documentos internos que não vão ao cliente | Tipo de documento "sem envio ao cliente" (PE-ENG-002) |
| Lista de ICS | Instruções de serviço, com módulo e projetos de referência | Mesma Lista, com outro tipo e campos extras |
| Lista de Doc. Externos | Recebidos de terceiros (fornecedor, concessionária) | Documentos externos (D-004) |

## Colunas da "Lista de documentos", agrupadas

- **Identificação:** sigla, linha, trecho, subtrecho, unidade, etapa, classe/subclasse,
  sequencial, código, revisão, versão. Na plataforma, isso sai do perfil de contrato: o código
  é interpretado, e não digitado em partes.
- **Calculadas pelo macro:** emissão inicial / rótulo cronológico (N), última revisão (O), dias
  de elaboração (X), situação (AC) e status atual. Na plataforma, viram **cálculo automático**,
  e não um botão "atualizar".
- **Descrição:** nome do trecho, elaboração (quem fez), modalidade, etapa, estrutura
  (disciplina), descrição e fase.
- **Fluxo com o cliente:** data de recebimento/elaboração, data de emissão, emissão (MR/GRD),
  data de análise, dias de análise, situação real, situação e retorno.
- **Fluxo interno:** análise interna, data e número da circular (PE-ENG-002).
- **Distribuição por setor** (Produção, Topografia, Qualidade): para cada um, GRD, data de envio
  e "em campo". É o controle de cópias distribuídas, ligado às GRDs que já existem.
- **Concessionárias:** data de envio, tratativas, data de análise, situação e formalização.
  É uma segunda cadeia de análise, paralela à do cliente.
- **Comercial/medição:** medição, valor da medição, total do contrato, nº do contrato, tipo,
  medição de referência. É a medição de terceiros (D-004).
- Observação.

## O que o macro calcula, e a gambiarra (D-022)

- `ColunaAC`, a situação da emissão:
  - sem data de emissão → "A EMITIR";
  - com emissão e sem data de análise → "EM ANÁLISE";
  - analisada → a situação é **deduzida da linha seguinte** do mesmo código:
    - se a próxima linha é a mesma revisão com versão maior: NÃO CONFORME (revisão de
      aprovação) ou INCONSISTENTE (preliminar);
    - senão: APROVADO (revisões 0/A/B…) ou NÃO APROVADO.
- **Por isso o dono precisa criar a linha da próxima revisão antes de recebê-la:** sem a
  "linha seguinte", o macro não sabe dizer se a análise reprovou. Um valor com `_` (ex.:
  `APROVADO_`) é a trava manual que o macro não sobrescreve.
- `ColunaN` / `ColunaO` / `ColunaX`: ordenam as emissões do código por data, rotulam (Emissão
  Inicial, Revisão N) e calculam os dias entre emissões.

## Como a plataforma resolve (proposta para o Marco da Lista Mestra)

1. O resultado da análise é um **fato registrado** (situação + data + documento de retorno,
   como RV/IT), e não uma dedução. A próxima emissão esperada é calculada pelo ciclo do perfil
   (block-016): depois de "Não aprovado", o sistema já sabe que a próxima é Rev N+1 Ver 1 e a
   mostra como "aguardando nova revisão", sem linha fictícia.
2. A **trava manual** vira uma correção explícita com motivo e histórico (auditoria, D-006).
3. Os cálculos de rótulo, dias e última revisão acontecem sempre que um dado muda, sem botão.
4. As cadeias de análise (interna → CQP → cliente → concessionária) são etapas configuráveis do
   perfil (estudo do perfil de contrato, item 9).
5. A distribuição por setor reaproveita as GRDs (Marco 14).
6. Croquis, ICS e externos são **tipos** dentro da mesma Lista, e não abas separadas.
