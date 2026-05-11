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
from app.session import set_contrato_ativo

st.set_page_config(
    page_title="Lista Mestra",
    page_icon="🏠",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Dados
# ---------------------------------------------------------------------------

def _verificar_banco() -> bool:
    try:
        with get_connection() as conn:
            conn.execute("SELECT 1 FROM contratos LIMIT 1")
        return True
    except Exception:
        return False


def _listar_contratos() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                c.id, c.nome, c.cliente,
                (SELECT COUNT(*) FROM documentos_previstos dp WHERE dp.contrato_id = c.id) AS previstos,
                (SELECT COUNT(*) FROM documentos d WHERE d.contrato_id = c.id) AS documentos,
                (SELECT COUNT(*) FROM revisoes r
                 JOIN documentos d2 ON d2.id = r.documento_id
                 WHERE d2.contrato_id = c.id) AS revisoes
            FROM contratos c
            WHERE c.ativo = 1
            ORDER BY c.nome
            """
        ).fetchall()
    return [dict(r) for r in rows]


def _criar_contrato(nome: str, cliente: str) -> int:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO contratos (nome, cliente) VALUES (?, ?)", (nome, cliente)
        )
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _home() -> None:
    st.title("Lista Mestra")

    # -----------------------------------------------------------------------
    # Verificação do banco
    # -----------------------------------------------------------------------

    if not _verificar_banco():
        st.error("Banco de dados não encontrado. Execute `python scripts/init_db.py` primeiro.")
        st.stop()

    # -----------------------------------------------------------------------
    # Grade de contratos
    # -----------------------------------------------------------------------

    contratos = _listar_contratos()

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
                novo_id = _criar_contrato(nome_inp.strip(), cliente_inp.strip())
                set_contrato_ativo(novo_id, nome_inp.strip(), cliente_inp.strip())
                st.success(f"Contrato **{nome_inp.strip()}** criado com sucesso.")
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
