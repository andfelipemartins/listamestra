# ADR 0004: Recebimento de GRD por token (preparação de domínio)

Data: 2026-06-09

Status: Aceita

## Contexto

A GRD (Guia de Remessa de Documentos) já é uma entidade operacional no SCLME,
com ciclo formal de status (rascunho → emitida → enviada → recebida, e anulada
como ramo excepcional). Falta fechar o ciclo com a confirmação de recebimento
pelo destinatário.

O destinatário muitas vezes está fora da empresa e não deve precisar acessar o
SCLME completo. A confirmação precisa ser simples, distribuível por qualquer
canal, e não depender de e-mail obrigatório.

## Decisão

Preparar o domínio e o banco para recebimento por link/token, **sem implementar
a rota/página pública agora**. Esta etapa entrega:

- campos de banco: `token_recebimento`, `token_recebimento_criado_em`,
  `recebido_em`, `recebido_por`, `recebido_cargo`, `declaracao_recebimento`,
  `motivo_anulacao`, `anulada_em`;
- regras de domínio no `GrdService`/`GrdRepository`:
  `gerar_token_recebimento`, `buscar_por_token`,
  `registrar_recebimento_por_token`, `marcar_recebida`;
- o token é gerado com `secrets.token_urlsafe` (CSPRNG).

A rota pública de confirmação será um **block futuro**.

## Direção arquitetural

- **Django + PostgreSQL** é o destino provável futuro do produto corporativo.
  A migração NÃO será feita agora.
- **FastAPI** é um adapter temporário aceitável para validar o recebimento por
  link antes da migração para Django. Quando implementado, deve consumir os
  mesmos `core/services` e `core/repositories`, sem reescrever regra de domínio.
- **Streamlit NÃO será usado** para a página pública de confirmação.
- **Google Forms está descartado.**
- **E-mail não é obrigatório.** O link/token pode ser distribuído por qualquer
  canal: WhatsApp, e-mail, Teams, QR Code, abertura direta no celular ou
  mensagem manual.

## Fluxo futuro (não implementado nesta etapa)

1. Usuário emite/envia a GRD.
2. Sistema gera token/link público único.
3. Usuário copia o link e distribui por qualquer meio.
4. Destinatário acessa uma página simples (fora do SCLME completo).
5. Destinatário informa nome, cargo/função, data e declaração de recebimento.
6. Sistema grava o recebimento (via `registrar_recebimento_por_token`).
7. GRD vira `recebida` e fica imutável.

## Consequências Positivas

- Regra de domínio centralizada e reutilizável por qualquer adapter (FastAPI/Django).
- A interface pública pode evoluir sem reescrever as regras da GRD.
- Confirmação independente de e-mail e de qualquer ferramenta de formulário externa.

## Consequências Negativas / Pendências (hardening futuro)

- Token armazenado em texto no banco — aceitável para MVP interno; a rota pública
  futura deverá validar token + expiração e considerar hashing do token.
- Sem rota pública ainda: o token é preparado mas só utilizável quando o adapter
  for implementado.

## Fora do escopo desta etapa

Implementar FastAPI ou Django; criar a página pública real; envio automático de
e-mail; integração WhatsApp/Outlook/Teams; assinatura eletrônica avançada;
migração para PostgreSQL.
