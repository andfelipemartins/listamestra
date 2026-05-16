"""
main.py — Ponto de entrada do SCLME

Execute com:
    streamlit run main.py
"""

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))
from app.session import set_contrato_ativo
from core.services.contract_service import ContractService

st.set_page_config(
    page_title="Lista Mestra",
    page_icon="🏠",
    layout="wide",
)

_contract_service = ContractService()


def _home() -> None:
    st.title("Lista Mestra")

    # -----------------------------------------------------------------------
    # Verificação do banco
    # -----------------------------------------------------------------------

    if not _contract_service.verificar_banco():
        st.error("Banco de dados não encontrado. Execute `python scripts/init_db.py` primeiro.")
        st.stop()

    # -----------------------------------------------------------------------
    # Grade de contratos
    # -----------------------------------------------------------------------

    contratos = _contract_service.listar_contratos_com_metricas()

    if contratos:
        st.subheader("Contratos ativos")

        _COLS = 3
        for i in range(0, len(contratos), _COLS):
            grupo = contratos[i : i + _COLS]
            cols = st.columns(_COLS)
            for col, c in zip(cols, grupo):
                with col:
                    with st.container(border=True):
                        st.markdown(f"### {c['nome']}")
                        if c.get("cliente"):
                            st.caption(c["cliente"])

                        m1, m2, m3 = st.columns(3)
                        m1.metric("Previstos", c["previstos"])
                        m2.metric("Na Lista", c["documentos"])
                        m3.metric("Revisões", c["revisoes"])

                        if st.button(
                            "Selecionar →",
                            key=f"sel_{c['id']}",
                            use_container_width=True,
                            type="primary",
                        ):
                            set_contrato_ativo(c["id"], c["nome"], c.get("cliente") or "")
                            st.switch_page("pages/1_Dashboard.py")

        st.divider()
    else:
        st.info(
            "Nenhum contrato cadastrado ainda. "
            "Crie o primeiro contrato abaixo para começar."
        )

    # -----------------------------------------------------------------------
    # Formulário de novo contrato
    # -----------------------------------------------------------------------

    with st.expander("Novo contrato", expanded=not contratos):
        with st.form("form_novo_contrato", clear_on_submit=True):
            nome_inp = st.text_input(
                "Nome do contrato *",
                placeholder="Ex: Linha 15 — Trecho Ragueb Chohfi",
            )
            cliente_inp = st.text_input(
                "Cliente / Contratante",
                placeholder="Ex: Metrô de São Paulo",
            )
            criar = st.form_submit_button("Criar contrato", type="primary")

        if criar:
            if not nome_inp.strip():
                st.error("O nome do contrato é obrigatório.")
            else:
                dados = _contract_service.validar_dados_contrato(nome_inp, cliente_inp)
                novo_id = _contract_service.criar_contrato(dados["nome"], dados["cliente"])
                set_contrato_ativo(novo_id, dados["nome"], dados["cliente"])
                st.success(f"Contrato **{dados['nome']}** criado com sucesso.")
                st.switch_page("pages/2_Importacao.py")


pg = st.navigation(
    [
        st.Page(_home, title="HOME", icon=":material/home:", default=True),
        st.Page("pages/1_Dashboard.py", title="DASHBOARD", icon=":material/bar_chart:"),
        st.Page("pages/2_Importacao.py", title="IMPORTAR", icon=":material/file_upload:"),
        st.Page("pages/3_Comparacao.py", title="DETALHAMENTO", icon=":material/find_in_page:"),
        st.Page("pages/4_CadastroManual.py", title="CADASTRAR DOCUMENTO", icon=":material/edit_document:"),
        st.Page("pages/5_Documento.py", title="PESQUISAR DOCUMENTO", icon=":material/search:"),
    ]
)
pg.run()
