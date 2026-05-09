"""
main.py — Ponto de entrada do SCLME

Execute com:
    streamlit run main.py
"""

import streamlit as st

st.set_page_config(
    page_title="SCLME — Controle de Lista Mestra",
    page_icon="📋",
    layout="wide",
)

st.title("📋 SCLME — Sistema de Controle de Lista Mestra")
st.caption("Sistema de Controle de Projetos Executivos · Linha 15 — Metrô de SP")

st.info(
    "🔧 Sistema em desenvolvimento. "
    "Navegue pelas páginas no menu lateral quando disponíveis.",
    icon="ℹ️",
)

# --- Demonstração do parser (Marco 1) ---
st.divider()
st.subheader("🔍 Teste do Parser de Código Documental")

from core.parsers.registry import ParserRegistry
from core.parsers.base_parser import CodigoParseado

registry = ParserRegistry()

codigo = st.text_input(
    "Informe um código documental:",
    value="DE-15.25.00.00-6A1-1001",
    help="Exemplo: DE-15.25.00.00-6A1-1001",
)

if codigo:
    resultado = registry.parse(codigo)

    if isinstance(resultado, CodigoParseado):
        st.success(f"✅ Código válido — {resultado.descricao_tipo}")

        col1, col2, col3 = st.columns(3)
        col1.metric("Tipo", resultado.tipo)
        col1.metric("Descrição", resultado.descricao_tipo)

        col2.metric("Trecho", resultado.extras.get("nome_trecho", "—"))
        col2.metric("Etapa", resultado.extras.get("etapa", "—"))

        col3.metric("Classe", resultado.extras.get("descricao_classe", "—"))
        col3.metric("Sequencial", resultado.extras.get("sequencial", "—"))

        st.caption(f"Identificador base: `{resultado.identificador_base}`")
        st.caption(f"Parser usado: `{resultado.parser_usado}`")

        if resultado.extras.get("avisos"):
            for aviso in resultado.extras["avisos"]:
                st.warning(f"⚠️ {aviso}")
    else:
        st.error(f"❌ {resultado.mensagem}")
        if resultado.detalhe:
            st.caption(f"Detalhe técnico: {resultado.detalhe}")
