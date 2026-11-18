# Estudo: até onde vai o perfil de contrato configurável

*2026-11-18 · tarefa t12 · base: D-005, D-008, D-018 e `docs/contratos/casos-de-teste.md`*

Pergunta do dono (D-008): dá para descrever cada contrato por configuração, ou será preciso
adaptar o código a cada cliente, como serviço? Este estudo testa um modelo concreto com os três
padrões reais que temos (Metrô, SPObras e EMTU) e aponta onde ele quebra.

## O modelo proposto

Um perfil de contrato tem quatro partes, todas declarativas (dados, não código):

1. **Código documental:** lista ordenada de *segmentos*, cada um com nome, significado,
   formato (dígitos, letras, tamanho) e, quando houver, uma tabela fechada de valores válidos.
   Separadores entre segmentos são explícitos.
2. **Identificação da emissão:** um ou dois eixos (revisão e, opcionalmente, versão), cada um
   com seu *alfabeto* (números, letras, letra + número), letras proibidas e regra de
   transbordo. Também diz se a revisão faz parte do código ou fica fora dele.
3. **Ciclo de análise:** uma máquina de estados. Os estados são as situações do cliente
   (Em análise, Aprovado, Não aprovado…), e cada transição diz o que acontece com a
   revisão/versão (nova versão, nova revisão preliminar, emissão original, fim de linha).
4. **Vocabulário e etapas:** tipos de documento, carimbos, etapas de análise em cadeia
   (interna → CQP → cliente) e indicadores (D-016 e PE-ENG).

Cada perfil tem **versão com data de vigência**, porque contratos antigos seguem o manual em
vigor na assinatura (SPObras 4.1).

### Exemplo 1: Metrô (MAN-10-201 + MAN-10-207 + prática do PW)

```yaml
codigo:
  # DE-15.25.00.00-6A1-1001
  segmentos:
    - {nome: tipo,       formato: "[A-Z]{2,4}", valores: tabela_tipos}
    - {sep: "-"}
    - {nome: linha,      formato: "\\d{2}"}
    - {sep: "."}
    - {nome: trecho,     formato: "\\d{2}", valores: tabela_trechos}
    - {sep: "."}
    - {nome: subtrecho,  formato: "\\d{2}"}
    - {sep: "."}
    - {nome: unidade,    formato: "\\d{2}"}
    - {sep: "-"}
    - {nome: etapa,      formato: "\\d"}
    - {nome: classe,     formato: "[A-I]"}
    - {nome: subclasse,  formato: "\\d{1,2}"}
    - {sep: "-"}
    - {nome: sequencial, formato: "\\d{4}"}
  revisao_no_codigo: false

emissao:
  revisao:
    preliminar:  {serie: numerica, inicio: 1}           # 1, 2, 3…
    original:    {serie: "0 depois letras", proibidas: [O], transbordo: "Z→AA"}
    reabertura:  {serie: "letra_proposta + numero"}     # A1, A2… → A
  versao: {serie: numerica, inicio: 1, origem: "GED/PW"}

analise:
  inicial: EM_ANALISE
  transicoes:
    NAO_CONFORME:  nova_versao
    INCONSISTENTE: {acao: nova_versao, bloqueia_medicao: true}
    NAO_APROVADO:  nova_revisao_preliminar
    APROVADO:      emitir_original
    CANCELADO:     fim_de_linha
```

### Exemplo 2: SPObras (MP-SQ-SP-00-9R-001 rev. L)

```yaml
codigo:
  # XX-CC-EE-WW-PY-ZZZ-R
  segmentos:
    - {nome: classificacao, formato: "[A-Z]{2}", valores: tabela_classificacao}
    - {sep: "-"}
    - {nome: programa,  formato: "\\w{2}"}
    - {sep: "-"}
    - {nome: trecho,    formato: "\\w{2}"}
    - {sep: "-"}
    - {nome: subtrecho, formato: "\\w{2}"}
    - {sep: "-"}
    - {nome: estagio,   formato: "\\d",    valores: {0: "Serviços Preliminares", 4: "Projeto Básico"}}
    - {nome: classe,    formato: "[A-Z]",  valores: {A: Arquitetura, C: "Estruturas de Concreto"}}
    - {sep: "-"}
    - {nome: sequencial, formato: "\\d{3}"}
    - {sep: "-"}
    - {nome: revisao,    formato: "[A-Z]|\\d+"}
  revisao_no_codigo: true

emissao:
  revisao:
    preliminar: {serie: letras, inicio: A, continua_apos_aprovacao: true}  # A, B, C → 1 → D, E → 2
    original:   {serie: numerica, inicio: 1}
  versao: null

analise:
  inicial: EM_ANALISE
  transicoes:
    APROVADO:               emitir_original
    APROVADO_COM_RESSALVAS: emitir_original   # a confirmar com o dono
    NAO_APROVADO:           nova_revisao_preliminar
    A_REVISAR:              nova_revisao_preliminar
```

### EMTU (IT-GPO-052/2012)

O PDF é escaneado e não foi lido. Pelo relato do dono, o código é parecido com o do Metrô e a
revisão é alfabética, virando número na aprovação. Cabe no mesmo modelo de série
"letras → número", parecido com o da SPObras. **Não validado.**

## Resultado: o que cabe e o que não cabe

**Cabe por configuração (cerca de 90% do que vimos):**
- segmentos com separadores diferentes, tamanhos e tabelas de valores;
- revisão dentro ou fora do código;
- séries numéricas, alfabéticas e mistas, com letras proibidas e transbordo;
- dois eixos (revisão × versão) ou um só;
- máquina de estados de análise com ações padronizadas;
- vocabulário (tipos, carimbos e situações), etapas de análise e indicadores;
- perfil com versão por vigência.

**Limites, onde a configuração pura quebra:**
1. **Regras com condição entre segmentos:** por exemplo, "se o tipo é DE, a subclasse é
   obrigatória" ou "o trecho 00 só vale com a unidade 00". Uma tabela de valores não expressa
   isso. Solução: permitir *restrições simples* no perfil (`se segmento X = v, então Y em
   [...]`). Mais que isso vira linguagem de programação.
2. **Séries de revisão exóticas:** a regra da SPObras "continua as letras depois da aprovação"
   (A, B, C → 1 → D, E → 2) é diferente da do Metrô, que reinicia (0 → A1, A2 → A). Isso exige
   um conjunto **finito de séries pré-programadas**, que o admin escolhe. Inventar uma série
   nova exige código.
3. **Casos especiais do manual** (MAN-10-201 5.3: terminais rodoviários e o código da Linha 9 –
   Geral) são exceções de domínio. Entram como *perfis derivados* ou como restrições do item 1.
4. **Interpretar o manual** continua sendo trabalho humano (ou de IA). O perfil descreve o
   padrão, mas alguém precisa ler o manual e preenchê-lo. Esse é o serviço de configuração
   assistida por IA que D-005 já previu.

## Conclusão e recomendação

A configuração genérica **é viável**. Os dois padrões completos que temos (Metrô e SPObras)
cabem no mesmo modelo, e o EMTU provavelmente também.

O formato recomendado é **híbrido**:
- **configuração** para segmentos, valores, vocabulário, etapas e a máquina de análise;
- uma **biblioteca de séries de revisão e de ações**, escrita em código e testada, da qual o
  admin escolhe as peças;
- **restrições simples** entre segmentos;
- um **serviço de configuração com IA**, que lê o manual e propõe o perfil, revisado por uma
  pessoa.

Um contrato que exigir uma série ou uma ação nova ganha uma peça nova na biblioteca, e não um
fork do produto. Isso responde ao "e se a configuração genérica for inviável?" do D-008: o
pior caso é acrescentar uma peça na biblioteca, não adaptar o produto inteiro.

**Próximo passo técnico** (depois do ADR de stack): implementar o motor de perfil em `core/`
(Python puro, sem stack) com os dois perfis acima como testes de aceitação. Os mesmos testes
viram o critério de "o modelo é bom o suficiente" (D-005).

**Para confirmar com o dono:**
- Na SPObras, "Aprovado com ressalvas" gera emissão final ou exige nova letra?
- Existem exemplos reais de código SPObras para validar os formatos de CC, EE e WW?
