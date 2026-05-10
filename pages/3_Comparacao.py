"""
pages/3_Comparacao.py

Comparação entre o Índice de Documentos (ID) e a Lista de Documentos.
Identifica ausentes, extras e divergências de título.
"""

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db.connection import get_connection
from core.engine.comparacao import comparar_id_lista
from core.exporters.excel_exporter import exportar_comparacao

st.set_page_config(page_title="Comparação ID × Lista — SCLME", page_icon="🔍", layout="wide")


# ---------------------------------------------------------------------------
# Contrato ativo
# ---------------------------------------------------------------------------

def _contrato_ativo():
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, nome, cliente FROM contratos WHERE ativo = 1 ORDER BY id LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


contrato = _contrato_ativo()

if contrato is None:
    st.title("🔍 Comparação ID × Lista")
    st.warning(
        "Nenhum contrato encontrado. "
        "Acesse **Importação** no menu lateral para criar o contrato e carregar os dados."
    )
    st.stop()

st.title(f"🔍 Comparação ID × Lista — {contrato['nome']}")
if contrato.get("cliente"):
    st.caption(contrato["cliente"])

# ---------------------------------------------------------------------------
# Executa comparação
# ---------------------------------------------------------------------------

resultado = comparar_id_lista(contrato["id"])

if resultado.total_previstos == 0:
    st.info(
        "Nenhum documento previsto encontrado. "
        "Importe o **Índice de Documentos (ID)** na página Importação."
    )
    st.stop()

# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------

c0, c1, c2, c3, c4 = st.columns(5)
c0.metric("Previstos (ID)", resultado.total_previstos)
c1.metric(
    "Encontrados na Lista",
    resultado.total_encontrados,
    f"{resultado.total_encontrados / resultado.total_previstos * 100:.1f}%",
)
c2.metric("Ausentes na Lista", resultado.total_ausentes, delta_color="inverse")
c3.metric("Extras na Lista", resultado.total_extras, delta_color="inverse")
c4.metric("Divergências de Título", resultado.total_divergencias, delta_color="inverse")

# ---------------------------------------------------------------------------
# Estado saudável
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### Exportar")
    nome_arquivo = contrato["nome"].replace(" ", "_")
    st.download_button(
        "⬇️ Comparação ID × Lista (.xlsx)",
        data=exportar_comparacao(resultado, contrato["nome"]),
        file_name=f"Comparacao_{nome_arquivo}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

if resultado.total_ausentes == 0 and resultado.total_extras == 0 and resultado.total_divergencias == 0:
    st.success("ID e Lista estão sincronizados — nenhuma inconsistência encontrada.")
    st.stop()

st.divider()

# ---------------------------------------------------------------------------
# Tabs de detalhe
# ---------------------------------------------------------------------------

_COLUNAS_BASE = {
    "codigo": "Código",
    "tipo": "Tipo",
    "nome_trecho": "Trecho",
    "titulo": "Título",
}

tab_ausentes, tab_extras, tab_diverg = st.tabs([
    f"Ausentes na Lista ({resultado.total_ausentes})",
    f"Extras na Lista ({resultado.total_extras})",
    f"Divergências de Título ({resultado.total_divergencias})",
])

with tab_ausentes:
    if resultado.ausentes.empty:
        st.success("Nenhum documento previsto ausente na Lista.")
    else:
        st.caption(
            "Documentos presentes no Índice (ID) que ainda não têm entrada na Lista de Documentos."
        )
        df = resultado.ausentes
        colunas = [c for c in _COLUNAS_BASE if c in df.columns]
        st.dataframe(
            df[colunas].rename(columns=_COLUNAS_BASE),
            use_container_width=True,
            hide_index=True,
        )

with tab_extras:
    if resultado.extras.empty:
        st.success("Nenhum documento extra encontrado na Lista.")
    else:
        st.caption(
            "Documentos presentes na Lista de Documentos que não constam no Índice (ID)."
        )
        df = resultado.extras
        colunas = [c for c in _COLUNAS_BASE if c in df.columns]
        st.dataframe(
            df[colunas].rename(columns=_COLUNAS_BASE),
            use_container_width=True,
            hide_index=True,
        )

with tab_diverg:
    if resultado.divergencias.empty:
        st.success("Nenhuma divergência de título encontrada.")
    else:
        st.caption(
            "Documentos presentes nos dois lados, mas com títulos diferentes entre o ID e a Lista."
        )
        df = resultado.divergencias
        colunas_div = {
            "codigo": "Código",
            "tipo": "Tipo",
            "nome_trecho": "Trecho",
            "titulo_id": "Título (ID)",
            "titulo_lista": "Título (Lista)",
        }
        colunas = [c for c in colunas_div if c in df.columns]
        st.dataframe(
            df[colunas].rename(columns=colunas_div),
            use_container_width=True,
            hide_index=True,
        )
