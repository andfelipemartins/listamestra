"""
pages/6_GRD.py

GRD (Guia de Remessa de Documentos) como entidade operacional.

Duas áreas:
- "Nova GRD": cabeçalho único (número, data, destinatário, A/C, obra, status),
  seleção de documentos com cópias por formato (A0–A4/Digital) e criação em lote
  com snapshot congelado.
- "Consultar GRDs": busca/filtros, abertura de GRD com itens, download Excel/PDF,
  alteração de status e cancelamento.

A página apenas captura inputs, chama o GrdService e exibe/oferece downloads.
Toda regra de negócio fica no service.
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
from app.session import require_contrato, sidebar_contexto
from core.auth.permissions import require_permission, widget_seletor_perfil

st.set_page_config(page_title="GRD — SCLME", page_icon="📦", layout="wide")

widget_seletor_perfil()
contrato = require_contrato()
sidebar_contexto()
require_permission("create_document")

_service = GrdService()

st.title("GRD — Guia de Remessa")
st.caption(f"Contrato: **{contrato['nome']}**")


def _iso(val) -> Optional[str]:
    if val is None:
        return None
    if hasattr(val, "isoformat") and val != date(1900, 1, 1):
        return val.isoformat()
    return None


aba_nova, aba_consulta = st.tabs(["Nova GRD", "Consultar GRDs"])

# ===========================================================================
# Nova GRD
# ===========================================================================
with aba_nova:
    st.subheader("Cabeçalho da GRD")
    st.caption("Preenchido uma vez e aplicado a todos os documentos selecionados.")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.text_input("Número da GRD", key="grd_numero", placeholder="Ex: GRD-001/2026")
        st.text_input("Destinatário", key="grd_destinatario", placeholder="Ex: METRÔ-SP")
        st.text_input("A/C", key="grd_ac", placeholder="aos cuidados de…")
    with c2:
        st.date_input("Data de envio", value=None, key="grd_data_envio", format="DD/MM/YYYY")
        st.text_input("Obra", key="grd_obra", placeholder="Ex: Linha 15")
        st.text_input("Emitido por", key="grd_emitido_por", placeholder="responsável")
    with c3:
        st.text_input("Trecho", key="grd_trecho", placeholder="Ex: 25 — Ragueb Chohfi")
        st.text_input("Módulo", key="grd_modulo", placeholder="opcional")
        st.selectbox("Status inicial", options=["rascunho", "emitida"], key="grd_status")

    st.text_input("Observações", key="grd_observacoes", placeholder="opcional")

    st.divider()
    st.subheader("Documentos a incluir")
    st.caption("Marque os documentos e ajuste as cópias por formato (A0–A4 / Digital).")

    busca = st.text_input(
        "Filtrar documentos", key="grd_busca",
        placeholder="código, título, trecho, estrutura, status…",
    )
    selecionaveis = _service.listar_documentos_selecionaveis(contrato["id"], busca)

    if not selecionaveis:
        st.info("Nenhum documento com revisão disponível para compor a GRD.")
    else:
        base = pd.DataFrame([
            {
                "Incluir":   False,
                "Código":    d["codigo"],
                "Título":    (d.get("titulo") or "")[:50],
                "Trecho":    d.get("nome_trecho") or "—",
                "Revisão":   f"{d.get('label_revisao') or '—'}/v{d.get('versao') or 1}",
                "Status":    d.get("status_atual") or "—",
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
                "Código":  st.column_config.TextColumn("Código", disabled=True),
                "Título":  st.column_config.TextColumn("Título", disabled=True),
                "Trecho":  st.column_config.TextColumn("Trecho", disabled=True),
                "Revisão": st.column_config.TextColumn("Rev.", disabled=True, width="small"),
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
        filtro_numero = st.text_input("Número da GRD", key="grd_f_numero")
        filtro_codigo = st.text_input("Código de documento", key="grd_f_codigo")
    with f2:
        filtro_status = st.selectbox("Status", options=["(todos)", *STATUS_GRD], key="grd_f_status")
        filtro_dest = st.text_input("Destinatário / Setor", key="grd_f_dest")
    with f3:
        filtro_de = st.date_input("Envio de", value=None, key="grd_f_de", format="DD/MM/YYYY")
        filtro_ate = st.date_input("Envio até", value=None, key="grd_f_ate", format="DD/MM/YYYY")

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
            numero = g.get("numero_grd") or "(sem número)"
            envio = fmt_data(g.get("data_envio")) if g.get("data_envio") else "—"
            status = g.get("status") or "—"
            cancelada = status == "cancelada"
            marca = "🚫 " if cancelada else "📦 "
            titulo = f"{marca}{numero} — {status.upper()} · {g.get('total_itens', 0)} doc(s) · Envio {envio}"
            with st.expander(titulo):
                meta = []
                for campo, rotulo in [
                    ("destinatario", "Destinatário"), ("ac", "A/C"), ("obra", "Obra"),
                    ("trecho", "Trecho"), ("emitido_por", "Emitido por"),
                    ("recebido_por", "Recebido por"), ("observacoes", "Observações"),
                ]:
                    if g.get(campo):
                        meta.append(f"**{rotulo}:** {g[campo]}")
                if meta:
                    st.markdown(" · ".join(meta))

                itens = _service.listar_itens(g["id"])
                if itens:
                    st.dataframe(
                        pd.DataFrame([
                            {
                                "Código": it["codigo"], "Título": (it.get("titulo") or "")[:50],
                                "Rev.": f"{it.get('label_revisao') or '—'}/v{it.get('versao') or 1}",
                                "Situação": it.get("situacao") or "—",
                                "A0": it.get("qtd_a0", 0), "A1": it.get("qtd_a1", 0),
                                "A2": it.get("qtd_a2", 0), "A3": it.get("qtd_a3", 0),
                                "A4": it.get("qtd_a4", 0), "Digital": it.get("qtd_digital", 0),
                            }
                            for it in itens
                        ]),
                        use_container_width=True, hide_index=True,
                    )

                d1, d2, d3, d4 = st.columns(4)
                with d1:
                    st.download_button(
                        "⬇️ Excel", data=_service.exportar_excel(g["id"]) or b"",
                        file_name=f"GRD_{numero.replace('/', '-')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"grd_xls_{g['id']}", use_container_width=True,
                    )
                with d2:
                    st.download_button(
                        "⬇️ PDF", data=_service.exportar_pdf(g["id"]) or b"",
                        file_name=f"GRD_{numero.replace('/', '-')}.pdf",
                        mime="application/pdf",
                        key=f"grd_pdf_{g['id']}", use_container_width=True,
                    )
                with d3:
                    novo = st.selectbox(
                        "Alterar status", options=list(STATUS_GRD),
                        index=list(STATUS_GRD).index(status) if status in STATUS_GRD else 0,
                        key=f"grd_st_{g['id']}",
                    )
                    if st.button("Aplicar", key=f"grd_apl_{g['id']}", use_container_width=True):
                        st.success(_service.alterar_status(g["id"], novo).mensagem)
                        st.rerun()
                with d4:
                    if not cancelada and st.button(
                        "Cancelar GRD", key=f"grd_canc_{g['id']}", use_container_width=True
                    ):
                        st.warning(_service.cancelar_grd(g["id"]).mensagem)
                        st.rerun()
