"""
app/session.py

Estado de sessão compartilhado entre páginas do SCLME.
Centraliza seleção de contrato ativo e helpers de contexto de sidebar.
"""

import streamlit as st

from db.connection import get_connection

_KEY_ID      = "contrato_id"
_KEY_NOME    = "contrato_nome"
_KEY_CLIENTE = "contrato_cliente"


def get_contrato_ativo() -> dict | None:
    cid = st.session_state.get(_KEY_ID)
    if cid is None:
        return None
    return {
        "id":      cid,
        "nome":    st.session_state.get(_KEY_NOME, ""),
        "cliente": st.session_state.get(_KEY_CLIENTE, ""),
    }


def set_contrato_ativo(contrato_id: int, nome: str, cliente: str = "") -> None:
    st.session_state[_KEY_ID]      = contrato_id
    st.session_state[_KEY_NOME]    = nome
    st.session_state[_KEY_CLIENTE] = cliente


def require_contrato() -> dict:
    """
    Retorna o contrato ativo da sessão.
    Backward-compat: se nenhum estiver na sessão, auto-seleciona o primeiro
    contrato ativo do banco (mantém comportamento das páginas legadas).
    Para a página com aviso + link se não houver contrato cadastrado.
    """
    contrato = get_contrato_ativo()
    if contrato:
        return contrato

    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, nome, cliente FROM contratos WHERE ativo = 1 ORDER BY id LIMIT 1"
        ).fetchone()

    if row:
        d = dict(row)
        set_contrato_ativo(d["id"], d["nome"], d.get("cliente") or "")
        return {"id": d["id"], "nome": d["nome"], "cliente": d.get("cliente") or ""}

    st.warning("Nenhum contrato encontrado. Crie um contrato na página inicial.")
    st.page_link("main.py", label="← Ir para Contratos", icon="🏠")
    st.stop()


def sidebar_contexto() -> None:
    """Exibe o contrato ativo e perfil na sidebar. Sem-op se não houver contrato."""
    contrato = get_contrato_ativo()
    if contrato:
        with st.sidebar:
            st.caption(f"📋 **{contrato['nome']}**")
            if contrato.get("cliente"):
                st.caption(contrato["cliente"])
