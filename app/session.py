"""
app/session.py

Estado de sessão compartilhado entre páginas do SCLME.
Centraliza seleção de contrato ativo e helpers de contexto de sidebar.
"""

import streamlit as st

from core.services.contract_service import ContractService

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

    contrato_ativo = ContractService().obter_contrato_ativo()
    if contrato_ativo:
        set_contrato_ativo(
            contrato_ativo["id"],
            contrato_ativo["nome"],
            contrato_ativo.get("cliente") or "",
        )
        return {
            "id": contrato_ativo["id"],
            "nome": contrato_ativo["nome"],
            "cliente": contrato_ativo.get("cliente") or "",
        }

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
