"""
core/auth/permissions.py

Controle de perfis e permissões (baseado em session_state — sem autenticação real).
"""

import streamlit as st

PERMISSOES = frozenset({
    "view_dashboard",
    "view_document",
    "view_comparison",
    "import_data",
    "create_document",
    "export_data",
    "manage_contracts",
})

PERFIS: dict[str, dict] = {
    "admin": {
        "label": "Administrador",
        "permissions": PERMISSOES,
    },
    "editor": {
        "label": "Controle Documental",
        "permissions": frozenset({
            "view_dashboard",
            "view_document",
            "view_comparison",
            "import_data",
            "create_document",
            "export_data",
        }),
    },
    "reader": {
        "label": "Leitor / Consulta",
        "permissions": frozenset({
            "view_dashboard",
            "view_document",
            "view_comparison",
            "export_data",
        }),
    },
    "visitor": {
        "label": "Visitante",
        "permissions": frozenset({"view_dashboard"}),
    },
}


def can_perfil(permission: str, perfil: str) -> bool:
    """Pure — testável sem Streamlit."""
    return permission in PERFIS.get(perfil, {}).get("permissions", frozenset())


def can(permission: str) -> bool:
    return can_perfil(permission, st.session_state.get("perfil", "admin"))


def require_permission(permission: str) -> None:
    if not can(permission):
        st.error("Acesso negado — seu perfil não tem permissão para esta função.")
        st.stop()


def widget_seletor_perfil() -> None:
    """Seletor de perfil na sidebar (modo dev). Persiste em session_state."""
    with st.sidebar:
        opcoes = {v["label"]: k for k, v in PERFIS.items()}
        perfil_atual = st.session_state.get("perfil", "admin")
        label_atual = PERFIS[perfil_atual]["label"]
        novo_label = st.selectbox(
            "Perfil (dev)",
            list(opcoes.keys()),
            index=list(opcoes.keys()).index(label_atual),
            key="_perfil_selector",
        )
        st.session_state["perfil"] = opcoes[novo_label]
