# Estudo G4: onde ficam os arquivos dos projetos

*Rascunho para conversa com o dono · 2026-11-18. Não é decisão.*

O dono ficou em dúvida (G4) e pediu os prós e contras de cada caminho. Ele considera a
integração com o SharePoint a opção menos necessária, porque depende da empresa, e vê no
armazenamento próprio a porta para leitura de PDFs e para o sistema virar um gerenciador
de contexto da obra (D-004), com o risco de virar um ProjectWise.

| | Só referência (caminho/link) | Integração com o SharePoint | Armazenamento próprio |
|---|---|---|---|
| Esforço inicial | Baixo | Alto (Graph API, OAuth, TI) | Médio |
| Depende da empresa/TI | Não | Sim | Só no deploy |
| Duplica arquivos | Não | Não | Sim |
| Link quebra se a pasta mudar | Sim | Menos (IDs estáveis) | Não |
| Leitura de PDF, busca e IA | Não, ou só com cópia local | Sim, via API | Sim, direto |
| Custo de espaço e backup | Nenhum | Nenhum extra | Cresce com a obra |
| Risco de virar "outro PW" | Nenhum | Baixo | Alto, se crescer sem limite |
| Projetista externo sobe arquivo (D-006) | Não resolve | Exige conta da empresa | Resolve |

**Ponto que pesa:** a resposta do B1 (D-006) pede que o projetista externo suba os
entregáveis pela plataforma. Só o armazenamento próprio atende a isso sem dar a ele
acesso ao SharePoint da empresa.

**Caminho sugerido para discutir (em etapas):**
1. Agora: só referência, que é leve e já evolui o que existe (leitura de nomes de arquivo).
2. Quando houver o portal do projetista: armazenamento próprio **só dos entregáveis
   recebidos** (recepção, com registro de versão e revisão), não um repositório geral
   da obra.
3. Leitura de conteúdo e IA vêm depois, sobre os arquivos recebidos.
4. SharePoint só se a empresa pedir.

O modelo de dados deve tratar o "local do arquivo" como um campo trocável (referência ou
armazenamento) para não travar nenhuma das etapas. Isso também depende da decisão de
stack (D-007), por causa do custo de armazenamento no deploy.
