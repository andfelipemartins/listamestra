"""
pages/6_GRD.py

GRD (Guia de Remessa de Documentos) como entidade operacional.

Duas Ã¡reas:
- "Nova GRD": cabeÃ§alho Ãºnico (nÃºmero, data, destinatÃ¡rio, A/C, obra, status),
  seleÃ§Ã£o de documentos com cÃ³pias por formato (A0â€“A4/Digital) e criaÃ§Ã£o em lote
  com snapshot congelado.
- "Consultar GRDs": busca/filtros, abertura de GRD com itens, download Excel/PDF,
  alteraÃ§Ã£o de status e cancelamento.

A pÃ¡gina apenas captura inputs, chama o GrdService e exibe/oferece downloads.
Toda regra de negÃ³cio fica no service.
"""

import os
import sys
from datetime import date
from typing import Optional

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.services.grd_service import GrdService
from core.repositories.grd_repository import STATUS_GRD
from core.formatacao import fmt_data
from core.config import PUBLIC_BASE_URL
from app.session import require_contrato, sidebar_contexto
from core.auth.permissions import require_permission, widget_seletor_perfil

st.set_page_config(page_title="GRD â€” SCLME", page_icon="ðŸ“¦", layout="wide")

widget_seletor_perfil()
contrato = require_contrato()
sidebar_contexto()
require_permission("create_document")

_service = GrdService()

st.title("GRD â€” Guia de Remessa")
st.caption(f"Contrato: **{contrato['nome']}**")


def _iso(val) -> Optional[str]:
    if val is None:
        return None
    if hasattr(val, "isoformat") and val != date(1900, 1, 1):
        return val.isoformat()
    return None


_TOKEN_OBS = (
    "A pagina publica de recebimento ainda nao esta implementada (block-008 / ADR 0004). "
    "Guarde/copie agora: o token nao sera exibido novamente; gerar de novo invalida o link anterior."
)


def _bloco_token(g: dict) -> None:
    """Exibe e gera token hardenizado; plaintext aparece apenas uma vez."""
    gid = g["id"]
    feedback = st.session_state.get("grd_token_feedback")

    if isinstance(feedback, dict) and feedback.get("grd_id") == gid:
        st.success("Token de recebimento gerado.")
        st.text_input(
            "Token de recebimento",
            value=feedback.get("token", ""),
            key=f"grd_tok_show_once_{gid}",
            disabled=True,
        )
        st.text_input(
            "Link futuro de recebimento",
            value=feedback.get("link", ""),
            key=f"grd_link_show_once_{gid}",
            disabled=True,
        )
        st.warning(_TOKEN_OBS)
        del st.session_state["grd_token_feedback"]
    elif g.get("token_hash") and not g.get("token_usado_em"):
        criado = fmt_data(g.get("token_recebimento_criado_em")) if g.get("token_recebimento_criado_em") else "â€”"
        expira = fmt_data(g.get("token_expira_em")) if g.get("token_expira_em") else "â€”"
        st.caption(
            f"Ha um token ativo gerado em {criado}, expira em {expira}. "
            "Renovar invalida o token atual."
        )
        st.info(_TOKEN_OBS)

    if st.button("Gerar/renovar token de recebimento", key=f"grd_gtok_{gid}", use_container_width=True):
        res = _service.gerar_token_recebimento(gid)
        if res.sucesso:
            token = (res.dados or {}).get("token") or res.mensagem
            st.session_state["grd_token_feedback"] = {
                "grd_id": gid,
                "token": token,
                "link": f"{PUBLIC_BASE_URL}/grd/receber/{token}",
            }
            st.rerun()
        else:
            st.warning(res.mensagem)


def _bloco_anular(g: dict) -> None:
    motivo = st.text_input(
        "Motivo da anulacao", key=f"grd_motivo_{g['id']}",
        placeholder="obrigatorio para anular",
    )
    if st.button("Anular GRD", key=f"grd_anul_{g['id']}", use_container_width=True):
        res = _service.anular_grd(g["id"], motivo)
        (st.success if res.sucesso else st.warning)(res.mensagem)
        if res.sucesso:
            st.rerun()


def _bloco_recebimento(g: dict) -> None:
    st.markdown("**Registrar recebimento (manual)**")
    rc1, rc2 = st.columns(2)
    with rc1:
        nome = st.text_input("Nome de quem recebeu *", key=f"grd_rnome_{g['id']}")
    with rc2:
        cargo = st.text_input("Cargo / FunÃ§Ã£o *", key=f"grd_rcargo_{g['id']}")
    data_rec = st.date_input("Data de recebimento", value=None,
                             key=f"grd_rdata_{g['id']}", format="DD/MM/YYYY")
    decl = st.text_input("DeclaraÃ§Ã£o (opcional â€” e-mail NÃƒO Ã© obrigatÃ³rio)",
                         key=f"grd_rdecl_{g['id']}")
    if st.button("Marcar como recebida", key=f"grd_rec_{g['id']}",
                 type="primary", use_container_width=True):
        res = _service.marcar_recebida(
            g["id"], nome, cargo, declaracao=decl, recebido_em=_iso(data_rec)
        )
        (st.success if res.sucesso else st.warning)(res.mensagem)
        if res.sucesso:
            st.rerun()


aba_nova, aba_consulta = st.tabs(["Nova GRD", "Consultar GRDs"])

# ===========================================================================
# Nova GRD
# ===========================================================================
with aba_nova:
    st.subheader("CabeÃ§alho da GRD")
    st.caption("Preenchido uma vez e aplicado a todos os documentos selecionados.")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.text_input("NÃºmero da GRD", key="grd_numero", placeholder="Ex: GRD-001/2026")
        st.text_input("DestinatÃ¡rio", key="grd_destinatario", placeholder="Ex: METRÃ”-SP")
        st.text_input("A/C", key="grd_ac", placeholder="aos cuidados deâ€¦")
    with c2:
        st.date_input("Data de envio", value=None, key="grd_data_envio", format="DD/MM/YYYY")
        st.text_input("Obra", key="grd_obra", placeholder="Ex: Linha 15")
        st.text_input("Emitido por", key="grd_emitido_por", placeholder="responsÃ¡vel")
    with c3:
        st.text_input("Trecho", key="grd_trecho", placeholder="Ex: 25 â€” Ragueb Chohfi")
        st.text_input("MÃ³dulo", key="grd_modulo", placeholder="opcional")
        st.selectbox("Status inicial", options=["rascunho", "emitida"], key="grd_status")

    st.text_input("ObservaÃ§Ãµes", key="grd_observacoes", placeholder="opcional")

    st.divider()
    st.subheader("Documentos a incluir")
    st.caption("Marque os documentos e ajuste as cÃ³pias por formato (A0â€“A4 / Digital).")

    busca = st.text_input(
        "Filtrar documentos", key="grd_busca",
        placeholder="cÃ³digo, tÃ­tulo, trecho, estrutura, statusâ€¦",
    )
    selecionaveis = _service.listar_documentos_selecionaveis(contrato["id"], busca)

    if not selecionaveis:
        st.info("Nenhum documento com revisÃ£o disponÃ­vel para compor a GRD.")
    else:
        base = pd.DataFrame([
            {
                "Incluir":   False,
                "CÃ³digo":    d["codigo"],
                "TÃ­tulo":    (d.get("titulo") or "")[:50],
                "Trecho":    d.get("nome_trecho") or "â€”",
                "RevisÃ£o":   f"{d.get('label_revisao') or 'â€”'}/v{d.get('versao') or 1}",
                "Status":    d.get("status_atual") or "â€”",
                "A0": 0, "A1": 0, "A2": 0, "A3": 0, "A4": 0, "Digital": 0,
            }
            for d in selecionaveis
        ])
        editado = st.data_editor(
            base,
            key="grd_editor",
            use_container_width=True,
            hide_index=True,
            height=380,
            column_config={
                "Incluir": st.column_config.CheckboxColumn("Incluir", width="small"),
                "CÃ³digo":  st.column_config.TextColumn("CÃ³digo", disabled=True),
                "TÃ­tulo":  st.column_config.TextColumn("TÃ­tulo", disabled=True),
                "Trecho":  st.column_config.TextColumn("Trecho", disabled=True),
                "RevisÃ£o": st.column_config.TextColumn("Rev.", disabled=True, width="small"),
                "Status":  st.column_config.TextColumn("Status", disabled=True, width="small"),
                **{
                    f: st.column_config.NumberColumn(f, min_value=0, step=1, default=0, width="small")
                    for f in ("A0", "A1", "A2", "A3", "A4", "Digital")
                },
            },
        )

        itens = []
        for i, row in editado.iterrows():
            if bool(row["Incluir"]) and i < len(selecionaveis):
                itens.append({
                    "revisao_id": selecionaveis[i]["revisao_id"],
                    "qtd_a0": row["A0"], "qtd_a1": row["A1"], "qtd_a2": row["A2"],
                    "qtd_a3": row["A3"], "qtd_a4": row["A4"], "qtd_digital": row["Digital"],
                })

        st.caption(f"{len(itens)} documento(s) selecionado(s).")
        if st.button("Criar GRD", type="primary", disabled=len(itens) == 0, use_container_width=True):
            cabecalho = {
                "numero_grd":   st.session_state.get("grd_numero"),
                "data_envio":   _iso(st.session_state.get("grd_data_envio")),
                "setor":        st.session_state.get("grd_destinatario"),
                "destinatario": st.session_state.get("grd_destinatario"),
                "ac":           st.session_state.get("grd_ac"),
                "obra":         st.session_state.get("grd_obra"),
                "emitido_por":  st.session_state.get("grd_emitido_por"),
                "trecho":       st.session_state.get("grd_trecho"),
                "modulo":       st.session_state.get("grd_modulo"),
                "observacoes":  st.session_state.get("grd_observacoes"),
                "status":       st.session_state.get("grd_status") or "rascunho",
            }
            resultado = _service.criar_grd(contrato["id"], cabecalho, itens)
            if resultado.sucesso:
                st.success(resultado.mensagem)
            else:
                st.warning(resultado.mensagem)

# ===========================================================================
# Consultar GRDs
# ===========================================================================
with aba_consulta:
    st.subheader("Buscar GRDs")

    f1, f2, f3 = st.columns(3)
    with f1:
        filtro_numero = st.text_input("NÃºmero da GRD", key="grd_f_numero")
        filtro_codigo = st.text_input("CÃ³digo de documento", key="grd_f_codigo")
    with f2:
        filtro_status = st.selectbox("Status", options=["(todos)", *STATUS_GRD], key="grd_f_status")
        filtro_dest = st.text_input("DestinatÃ¡rio / Setor", key="grd_f_dest")
    with f3:
        filtro_de = st.date_input("Envio de", value=None, key="grd_f_de", format="DD/MM/YYYY")
        filtro_ate = st.date_input("Envio atÃ©", value=None, key="grd_f_ate", format="DD/MM/YYYY")

    filtros = {
        "numero": filtro_numero or None,
        "codigo": filtro_codigo or None,
        "status": None if filtro_status == "(todos)" else filtro_status,
        "destinatario": filtro_dest or None,
        "data_de": _iso(filtro_de),
        "data_ate": _iso(filtro_ate),
    }
    grds = _service.listar_grds(contrato["id"], {k: v for k, v in filtros.items() if v})

    if not grds:
        st.info("Nenhuma GRD encontrada.")
    else:
        st.caption(f"{len(grds)} GRD(s) encontrada(s).")
        for g in grds:
            numero = g.get("numero_grd") or "(sem nÃºmero)"
            envio = fmt_data(g.get("data_envio")) if g.get("data_envio") else "â€”"
            status = g.get("status") or "â€”"
            marca = "ðŸš« " if status == "anulada" else "ðŸ“¦ "
            titulo = f"{marca}{numero} â€” {status.upper()} Â· {g.get('total_itens', 0)} doc(s) Â· Envio {envio}"
            with st.expander(titulo):
                meta = []
                for campo, rotulo in [
                    ("destinatario", "DestinatÃ¡rio"), ("ac", "A/C"), ("obra", "Obra"),
                    ("trecho", "Trecho"), ("emitido_por", "Emitido por"),
                    ("recebido_por", "Recebido por"), ("observacoes", "ObservaÃ§Ãµes"),
                ]:
                    if g.get(campo):
                        meta.append(f"**{rotulo}:** {g[campo]}")
                if meta:
                    st.markdown(" Â· ".join(meta))

                itens = _service.listar_itens(g["id"])
                if itens:
                    st.dataframe(
                        pd.DataFrame([
                            {
                                "CÃ³digo": it["codigo"], "TÃ­tulo": (it.get("titulo") or "")[:50],
                                "Rev.": f"{it.get('label_revisao') or 'â€”'}/v{it.get('versao') or 1}",
                                "SituaÃ§Ã£o": it.get("situacao") or "â€”",
                                "A0": it.get("qtd_a0", 0), "A1": it.get("qtd_a1", 0),
                                "A2": it.get("qtd_a2", 0), "A3": it.get("qtd_a3", 0),
                                "A4": it.get("qtd_a4", 0), "Digital": it.get("qtd_digital", 0),
                            }
                            for it in itens
                        ]),
                        use_container_width=True, hide_index=True,
                    )

                # Aviso de congelamento (qualquer status != rascunho Ã© imutÃ¡vel nos itens)
                if status == "recebida":
                    st.info("ðŸ”’ GRD recebida â€” somente leitura (imutÃ¡vel).")
                elif status == "anulada":
                    st.warning(f"ðŸš« GRD anulada â€” somente leitura. Motivo: {g.get('motivo_anulacao') or 'â€”'}")
                elif status != "rascunho":
                    st.caption("ðŸ”’ Itens congelados â€” a GRD nÃ£o estÃ¡ mais em rascunho.")

                # Downloads (disponÃ­veis a partir de 'emitida')
                if status != "rascunho":
                    dcol1, dcol2 = st.columns(2)
                    with dcol1:
                        st.download_button(
                            "â¬‡ï¸ Excel", data=_service.exportar_excel(g["id"]) or b"",
                            file_name=f"GRD_{numero.replace('/', '-')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"grd_xls_{g['id']}", use_container_width=True,
                        )
                    with dcol2:
                        st.download_button(
                            "â¬‡ï¸ PDF", data=_service.exportar_pdf(g["id"]) or b"",
                            file_name=f"GRD_{numero.replace('/', '-')}.pdf",
                            mime="application/pdf",
                            key=f"grd_pdf_{g['id']}", use_container_width=True,
                        )

                # AÃ§Ãµes controladas por status (sem alteraÃ§Ã£o livre de status)
                if status == "rascunho":
                    a1, a2 = st.columns(2)
                    with a1:
                        if st.button("Emitir GRD", key=f"grd_emit_{g['id']}",
                                     type="primary", use_container_width=True):
                            res = _service.emitir_grd(g["id"])
                            (st.success if res.sucesso else st.warning)(res.mensagem)
                            st.rerun()
                    with a2:
                        if st.button("Excluir rascunho", key=f"grd_del_{g['id']}",
                                     use_container_width=True):
                            res = _service.excluir_rascunho(g["id"])
                            (st.success if res.sucesso else st.warning)(res.mensagem)
                            st.rerun()

                elif status == "emitida":
                    if st.button("Marcar como enviada", key=f"grd_env_{g['id']}",
                                 type="primary", use_container_width=True):
                        st.success(_service.marcar_enviada(g["id"]).mensagem)
                        st.rerun()
                    _bloco_token(g)
                    _bloco_anular(g)

                elif status == "enviada":
                    _bloco_recebimento(g)
                    _bloco_token(g)
                    _bloco_anular(g)

