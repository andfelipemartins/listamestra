"""
app/components/dados_derivados_codigo.py

Componente Streamlit para exibicao somente leitura dos dados derivados do
codigo documental.
"""

import streamlit as st


def _valor(valor) -> str:
    return str(valor) if valor not in (None, "") else "-"


def _campo(label: str, valor) -> None:
    st.markdown(f"**{label}:** {_valor(valor)}")


def exibir_dados_derivados_codigo(dados: dict) -> None:
    """Renderiza dados derivados como informacao somente leitura."""
    st.markdown("**Dados derivados do codigo**")

    with st.container(border=True):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            _campo("Tipo/Sigla", dados.get("tipo"))
            _campo("Linha", dados.get("linha"))
        with c2:
            _campo("Trecho", dados.get("trecho"))
            _campo("Nome do trecho", dados.get("nome_trecho"))
        with c3:
            _campo("Subtrecho", dados.get("subtrecho"))
            _campo("Unidade", dados.get("unidade"))
        with c4:
            _campo("Etapa/Fase", dados.get("etapa"))
            _campo("Sequencial", dados.get("sequencial"))

        c5, c6 = st.columns(2)
        with c5:
            _campo("Classe/Subclasse", dados.get("classe_subclasse"))
        with c6:
            disciplina = dados.get("disciplina")
            descricao = dados.get("disciplina_descricao")
            texto = f"{disciplina} - {descricao}" if descricao else disciplina
            _campo("Disciplina/Estrutura", texto)

    if dados and not dados.get("trecho_mapeado", False):
        st.warning("Trecho nao mapeado.")
    if dados and not dados.get("disciplina_mapeada", False):
        st.warning("Classe/Subclasse nao encontrada no cadastro de disciplinas.")
