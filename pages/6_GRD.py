"""
pages/6_GRD.py

Geração de GRD (Guia de Remessa de Documentos) em lote.

O usuário preenche o cabeçalho da GRD uma única vez (número, data de envio,
setor/destinatário, trecho, módulo, observações) e seleciona múltiplos
documentos/revisões em tabela. Uma GRD é criada e aplicada a todos os
selecionados de uma só vez. Regra de negócio fica no GrdService.
"""

import os
import sys
from datetime import date
from typing import Optional

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.services.grd_service import GrdService
from core.formatacao import fmt_data
from app.session import require_contrato, sidebar_contexto
from core.auth.permissions import require_permission, widget_seletor_perfil

st.set_page_config(page_title="Gerar GRD — SCLME", page_icon="📦", layout="wide")

widget_seletor_perfil()
contrato = require_contrato()
sidebar_contexto()
require_permission("create_document")

_service = GrdService()

st.title("Gerar GRD")
st.caption(f"Contrato: **{contrato['nome']}**")


def _iso(val) -> Optional[str]:
    if val is None:
        return None
    if hasattr(val, "isoformat") and val != date(1900, 1, 1):
        return val.isoformat()
    return None


# ---------------------------------------------------------------------------
# Cabeçalho da GRD (preenchido uma vez)
# ---------------------------------------------------------------------------

st.subheader("Cabeçalho da GRD")
st.caption("Preenchido uma vez e aplicado a todos os documentos selecionados.")

c1, c2, c3 = st.columns(3)
with c1:
    st.text_input("Número da GRD", key="grd_numero", placeholder="Ex: GRD-001/2026")
    st.text_input("Setor / Destinatário", key="grd_setor", placeholder="Ex: METRÔ / Produção")
with c2:
    st.date_input("Data de envio", value=None, key="grd_data_envio", format="DD/MM/YYYY")
    st.text_input("Trecho", key="grd_trecho", placeholder="Ex: 25 — Ragueb Chohfi")
with c3:
    st.text_input("Módulo", key="grd_modulo", placeholder="opcional")
    st.text_input("Observações", key="grd_observacoes", placeholder="opcional")

st.divider()

# ---------------------------------------------------------------------------
# Seleção de documentos/revisões
# ---------------------------------------------------------------------------

st.subheader("Documentos a incluir")

busca = st.text_input(
    "Filtrar documentos",
    key="grd_busca",
    placeholder="código, título, trecho, estrutura, status…",
)

selecionaveis = _service.listar_documentos_selecionaveis(contrato["id"], busca)

if not selecionaveis:
    st.info("Nenhum documento com revisão disponível para compor a GRD.")
    st.stop()

df = pd.DataFrame(
    [
        {
            "Código":    d["codigo"],
            "Título":    (d.get("titulo") or "")[:60],
            "Trecho":    d.get("nome_trecho") or "—",
            "Estrutura": d.get("disciplina_display") or "—",
            "Revisão":   f"{d.get('label_revisao') or '—'}/v{d.get('versao') or 1}",
            "Status":    d.get("status_atual") or "—",
            "Emissão":   fmt_data(d.get("data_emissao")) if d.get("data_emissao") else "—",
        }
        for d in selecionaveis
    ]
)

event = st.dataframe(
    df,
    key="grd_tabela_selecao",
    use_container_width=True,
    hide_index=True,
    selection_mode="multi-row",
    on_select="rerun",
    height=400,
)

selecionados_idx = event.selection.rows if event and event.selection else []
revisao_ids = [
    selecionaveis[i]["revisao_id"]
    for i in selecionados_idx
    if i < len(selecionaveis)
]

st.caption(f"{len(revisao_ids)} documento(s) selecionado(s).")

criar = st.button(
    "Criar GRD",
    type="primary",
    disabled=len(revisao_ids) == 0,
    use_container_width=True,
)

if criar:
    cabecalho = {
        "numero_grd":  st.session_state.get("grd_numero"),
        "data_envio":  _iso(st.session_state.get("grd_data_envio")),
        "setor":       st.session_state.get("grd_setor"),
        "trecho":      st.session_state.get("grd_trecho"),
        "modulo":      st.session_state.get("grd_modulo"),
        "observacoes": st.session_state.get("grd_observacoes"),
    }
    resultado = _service.criar_grd(contrato["id"], cabecalho, revisao_ids)
    if resultado.sucesso:
        st.success(resultado.mensagem)
    else:
        st.warning(resultado.mensagem)

st.divider()

# ---------------------------------------------------------------------------
# GRDs já criadas
# ---------------------------------------------------------------------------

st.subheader("GRDs criadas")

grds = _service.listar_grds(contrato["id"])
if not grds:
    st.info("Nenhuma GRD criada ainda.")
else:
    for g in grds:
        numero = g.get("numero_grd") or "(sem número)"
        envio = fmt_data(g.get("data_envio")) if g.get("data_envio") else "—"
        titulo = f"📦 {numero} — {g.get('total_itens', 0)} documento(s) · Envio {envio}"
        with st.expander(titulo):
            meta = []
            if g.get("setor"):
                meta.append(f"**Setor/Destinatário:** {g['setor']}")
            if g.get("trecho"):
                meta.append(f"**Trecho:** {g['trecho']}")
            if g.get("modulo"):
                meta.append(f"**Módulo:** {g['modulo']}")
            if g.get("observacoes"):
                meta.append(f"**Observações:** {g['observacoes']}")
            if meta:
                st.markdown(" · ".join(meta))

            itens = _service.listar_itens(g["id"])
            if itens:
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "Código":  it["codigo"],
                                "Título":  (it.get("titulo") or "")[:60],
                                "Revisão": f"{it.get('label_revisao') or '—'}/v{it.get('versao') or 1}",
                                "Situação": it.get("situacao") or "—",
                            }
                            for it in itens
                        ]
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
