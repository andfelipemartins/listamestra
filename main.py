"""
main.py — Ponto de entrada do SCLME

Execute com:
    streamlit run main.py
"""

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))
from db.connection import get_connection

st.set_page_config(
    page_title="SCLME — Controle de Lista Mestra",
    page_icon="📋",
    layout="wide",
)

st.title("📋 SCLME")
st.caption("Sistema de Controle de Lista Mestra de Projetos Executivos · Linha 15 — Metrô de SP")

# ---------------------------------------------------------------------------
# Estado do sistema
# ---------------------------------------------------------------------------

def _resumo():
    try:
        with get_connection() as conn:
            contratos = conn.execute(
                "SELECT COUNT(*) AS n FROM contratos WHERE ativo = 1"
            ).fetchone()["n"]
            previstos = conn.execute(
                "SELECT COUNT(*) AS n FROM documentos_previstos"
            ).fetchone()["n"]
            documentos = conn.execute(
                "SELECT COUNT(*) AS n FROM documentos"
            ).fetchone()["n"]
            revisoes = conn.execute(
                "SELECT COUNT(*) AS n FROM revisoes"
            ).fetchone()["n"]
        return dict(contratos=contratos, previstos=previstos,
                    documentos=documentos, revisoes=revisoes)
    except Exception:
        return None


resumo = _resumo()

if resumo is None:
    st.error("Banco de dados não encontrado. Execute `python scripts/init_db.py` primeiro.")
    st.stop()

# ---------------------------------------------------------------------------
# Cards de estado
# ---------------------------------------------------------------------------

c1, c2, c3, c4 = st.columns(4)
c1.metric("Contratos", resumo["contratos"])
c2.metric("Docs Previstos (ID)", resumo["previstos"])
c3.metric("Docs na Lista", resumo["documentos"])
c4.metric("Revisões", resumo["revisoes"])

st.divider()

# ---------------------------------------------------------------------------
# Ações rápidas
# ---------------------------------------------------------------------------

if resumo["contratos"] == 0 or resumo["previstos"] == 0:
    st.info(
        "**Primeiros passos:** acesse **Importação** no menu lateral para criar o contrato "
        "e carregar o Índice de Documentos (ID) e a Lista de Documentos."
    )
else:
    st.info("Acesse o **Dashboard** no menu lateral para ver o progresso do contrato.")

col_dash, col_imp = st.columns(2)
with col_dash:
    st.page_link("pages/1_Dashboard.py", label="Ir para o Dashboard", icon="📊")
with col_imp:
    st.page_link("pages/2_Importacao.py", label="Ir para Importação", icon="📥")
