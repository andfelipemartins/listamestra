# Estudo — IA dentro da plataforma: o que é, onde roda e qual caminho levar à empresa

*Origem: resposta M4 do dono (2026-11-18). Revisado depois da N3/N4 (D-033). Status: rascunho para
a conversa. Os valores de hardware e custo são estimativas de ordem de grandeza e precisam ser
conferidos antes de qualquer orçamento. Os nomes de produtos e serviços de nuvem mudam com
frequência: confirme com o TI o que existe no contrato da empresa.*

## 0. Respostas diretas às suas dúvidas da N3

**"A opção B seria uma API direta com o Copilot?"** Não. São coisas diferentes:

- O **Copilot** é um *produto pronto* da Microsoft: o chat que vem no Windows, no Office e no
  Teams. Ele é feito para qualquer pessoa e qualquer assunto. Não é pensado para outro programa
  conversar com ele com instruções precisas, por isso ele "erra 11 de 10" nas tarefas de
  engenharia. O problema não é só o modelo, é o produto genérico em volta.
- A **opção B** é alugar o *modelo* (o "cérebro") pela nuvem que a empresa já usa, sem o produto
  Copilot em volta. Na Microsoft, isso fica no serviço de IA do Azure (hoje chamado Azure AI
  Foundry, que inclui o Azure OpenAI). Lá a empresa contrata modelos de ponta (da OpenAI e, mais
  recentemente, também da Anthropic, ou seja, o Claude) e paga por uso. Na AWS, o equivalente é o
  Bedrock. No Google, é o Vertex AI.
- Então a resposta à sua pergunta "seria usar as LLMs deles?" é: **sim, usar modelos fortes
  hospedados na nuvem deles**. Quem fala com o modelo é a *nossa plataforma*, com as nossas
  instruções, o nosso perfil de contrato e o formato de resposta que nós exigimos. É por isso que o
  resultado fica muito melhor que o Copilot, mesmo que o modelo seja parecido.
- **Por que isso destrava na empresa:** se ela tem Microsoft 365 e Copilot, quase certamente
  já tem uma conta Microsoft corporativa. Ligar o Azure nessa conta é uma decisão do TI, e os dados
  ficam no contrato que eles já confiam. Talvez ainda não esteja ligado ("duvido muito", como você
  disse), e é justamente isso que você vai descobrir.

**O que perguntar ao TI (3 perguntas, por e-mail mesmo):**
1. Nós temos assinatura do Azure, ou só Microsoft 365?
2. Existe uma política sobre usar serviços de IA com documentos de clientes? Se sim, qual?
3. Se um projeto interno precisar de IA, quem aprova ligar o Azure AI Foundry/Azure OpenAI?

## 0.1 O assistente que vale a pena (não um chatbot de banco)

Você tem razão: a primeira lista era tímida. Um "chatbot de banco" **espera você perguntar**. O
assistente que faz diferença **trabalha sozinho e entrega o serviço pronto para você só
conferir**. A diferença é a mesma entre um atendente e um estagiário muito bom. Exemplos no
nosso domínio:

- **Conciliação automática do PW:** você sobe a extração e o assistente já devolve "12
  documentos mudaram de situação; 3 voltaram NÃO APROVADO, e aqui está o resumo do que o cliente
  pediu em cada RV; 2 estão no PW e fora do ID; quer que eu monte o ID parcial?".
- **Leitor de comentários (RV):** lê o PDF de comentários do cliente, quebra item por item, cria
  uma pendência por comentário, sugere o responsável pela disciplina (caixa classe) e acompanha
  até a próxima revisão fechar cada item.
- **Conferência de emissão antes de mandar:** antes da GRD, abre cada PDF e confere o carimbo
  contra o cadastro (código, revisão, título igual ao do ID, data). Pega o erro que geraria
  INCONSISTENTE *antes* de o cliente ver.
- **Montagem de ID parcial:** quando surgem documentos novos (D-032), propõe os códigos na
  sequência certa pelo perfil, o título no padrão e a planilha no formato de atributos do PW, pronta
  para subir.
- **Relatório da semana pronto:** toda sexta, o texto e os números para a reunião (o que andou, o
  que travou, o que está atrasado contra o cronograma do ID), no tom que a chefia gosta.
- **Configuração de contrato novo:** recebe os manuais (como fiz com o MAN-10-202) e entrega o
  perfil inteiro para o admin revisar. Isso transforma "semanas de configuração" em "uma tarde
  de revisão", e é um argumento de venda forte.
- **Perguntas livres com números de verdade:** "quanto da drenagem do trecho 25 está
  aprovado?" respondido a partir do banco, e não do achismo do modelo.

O princípio da seção 1 continua valendo para tudo isso: **a IA prepara, o humano confere e o motor
grava**. Quanto mais o assistente faz sozinho, mais importante é que cada proposta dele seja
fácil de revisar.

Para escolher por onde começar, a pergunta P4 do painel pede as 3 tarefas que mais comem o
seu tempo. O assistente começa por elas.

## 1. O que "integrar uma LLM" quer dizer aqui

A IA não fica "dentro" do programa como uma peça que pensa sozinha. A plataforma faz
**chamadas pontuais** a um modelo de linguagem para tarefas específicas: manda um texto (ou um PDF),
recebe de volta uma resposta estruturada (por exemplo um YAML de perfil) e **um humano revisa**
antes de qualquer coisa ser gravada.

Princípio que proponho como regra do produto:

> **A IA propõe, o admin aprova, o motor executa.** O motor de perfil, o ciclo de revisão e
> as pendências são determinísticos e funcionam sem IA. Se a IA ficar fora do ar, a plataforma
> continua funcionando: só perde o "assistente".

Esse princípio responde metade da preocupação: a IA nunca está no caminho crítico, então a
escolha de onde ela roda pode mudar depois sem reescrever nada.

## 2. Onde a IA ajudaria no SCLME (e com que frequência)

| Tarefa | Frequência | Peso do erro |
|---|---|---|
| Ler os manuais do órgão e propor o perfil (caixas, valores, ciclo de revisão) | 1 vez por contrato ou revisão de manual | Baixo, porque o admin revisa tudo |
| Ler o ID do PDF e propor a lista de previstos | Por emissão de ID | Médio |
| Conferir carimbo e título do PDF × cadastro (o título do ID bate com o do desenho?) | Diária | Médio |
| Ler o RV/comentários do cliente e resumir o que pediram | Por análise recebida | Baixo |
| Perguntas em linguagem natural ("quantos desenhos de drenagem estão não aprovados?") | Diária | Baixo |

A frequência é o que justifica ou não um servidor próprio. Só a configuração de perfil (rara)
**não** paga um servidor. As tarefas diárias de baixo para cima pagam.

## 3. As quatro opções

### A · API na nuvem, direto com o fornecedor (Anthropic, OpenAI…)
- **Qualidade:** a melhor disponível, inclusive para PDF com tabelas (como fiz com o MAN-10-202).
- **Dados:** o documento sai da empresa. Nos planos comerciais de API, os fornecedores em geral
  não treinam com os dados do cliente e têm política de retenção, mas isso **é exatamente o ponto
  que o TI/jurídico costuma barrar**.
- **Custo:** paga por uso. Para a configuração de perfil, é quase nada.

### B · Modelo forte pela nuvem que a empresa **já contratou** (Microsoft/Azure, AWS, Google)
- Se a empresa usa Copilot, ela tem contrato com a Microsoft. Os grandes provedores de nuvem
  revendem modelos de ponta (o Claude, por exemplo, aparece nos catálogos de AWS Bedrock e Google
  Vertex, e a Microsoft passou a oferecer modelos da Anthropic no ecossistema dela. **Vale
  confirmar com o TI o que está liberado no contrato de vocês.**).
- **Dados:** ficam dentro do contrato de nuvem que o TI já aprovou. É o argumento que mais
  costuma destravar.
- **Qualidade:** a mesma da opção A, porque o modelo é o mesmo e só muda o "balcão".
- **Copilot × modelo:** o Copilot que você usa é um produto de chat genérico. Aqui a plataforma
  chamaria o modelo com instruções e formato de saída controlados por nós, o que dá um resultado
  muito diferente.

### C · LLM local num servidor do escritório (a sua ideia)
- **Como funciona:** um modelo de pesos abertos (famílias como Llama, Qwen, Mistral, gpt-oss)
  rodando num servidor com GPU, servido por ferramentas como Ollama ou vLLM. A plataforma chama o
  servidor da sala como chamaria uma API.
- **Dados:** nada sai do prédio. Não depende de internet.
- **Qualidade:** abaixo dos modelos de ponta, principalmente para ler PDF longo com tabelas
  desalinhadas (como a Tabela 4 do MAN-10-202) e seguir um formato rígido. É suficiente para
  tarefas menores (resumir comentário, classificar, conferir título).
- **Custo e manutenção:** hardware com GPU de bastante memória (estimativa de ordem de grandeza:
  uma GPU de 24–48 GB para modelos médios; modelos maiores pedem mais), energia, refrigeração e
  alguém que mantenha. É um investimento de equipamento, e não uma assinatura.

### D · Híbrido (recomendado para desenhar o produto)
- A plataforma fala com um **"assistente" genérico** (uma interface única). Quem responde atrás
  dela é configurável: nuvem da empresa, servidor local ou nenhum.
- Tarefas que pedem qualidade alta e são raras (ler manual e propor o perfil) vão para o modelo
  forte (B). Tarefas diárias e sensíveis podem ir para o local (C), se um dia existir o servidor.
- Hoje, sem nada contratado, o "assistente" é este fluxo aqui: o Claude Code lê o manual e
  entrega o YAML, e o admin carrega pelo botão do block-017.

## 4. Recomendação

1. **Agora:** seguir pelo fluxo de fora da plataforma (Claude Code gera o perfil, o admin
   carrega). Não depende de ninguém e já prova o valor.
2. **No produto:** construir o ponto de encaixe do "assistente" com o princípio da seção 1, sem
   amarrar a nenhum fornecedor.
3. **Para a empresa:** levar a opção **B** como proposta principal (mesmo contrato de nuvem que o TI
   já aprova) e a **C** como alternativa se a política proibir nuvem. O argumento de magnitude que
   você levantou é mais forte com uma demonstração do que com orçamento: mostrar o perfil Metrô
   montado a partir do PDF e a Lista Mestra rodando com dados reais.
4. *(Pela N4, o servidor local está quase descartado e o teste na RTX 4060 Ti de 8 GB não seria
   representativo. Este item fica só como referência.)* **Antes de orçar servidor:** medir. Rodar um modelo local de teste neste computador (se a GPU
   permitir) com as mesmas tarefas e comparar com o resultado do modelo forte. Com esse número, a
   conversa sobre investimento fica concreta.

## 5. Perguntas que ficam para o dono

- O TI da empresa já tem algum contrato de nuvem (Azure/AWS/Google) além do Copilot?
- Existe política escrita sobre envio de documentos do cliente para serviços externos?
- O computador onde você desenvolve tem GPU dedicada? (para o teste do item 4.4)
