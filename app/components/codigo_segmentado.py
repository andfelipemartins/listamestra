"""
app/components/codigo_segmentado.py

Componente Streamlit para entrada segmentada de codigo documental.

O componente nao persiste dados. Ele apenas captura input, usa funcoes puras
do parser/builder e devolve o codigo final normalizado para a pagina.
"""

import streamlit as st

from core.parsers.codigo_builder import (
    LINHA15_TIPOS,
    LINHA15_TRECHOS,
    montar_codigo_segmentado_linha15,
    desmontar_codigo_linha15,
)


def _resultado(codigo="", partes=None, valido=False, mensagem="", modo="segmentado") -> dict:
    return {
        "codigo": codigo,
        "partes": partes or {},
        "valido": valido,
        "mensagem": mensagem,
        "modo": modo,
    }


def _format_tipo(tipo: str) -> str:
    return f"{tipo} - {LINHA15_TIPOS[tipo]}"


def _format_trecho(trecho: str) -> str:
    return f"{trecho} - {LINHA15_TRECHOS[trecho]}"


def _classe_subclasse(valor: str) -> tuple[str, str]:
    texto = (valor or "").strip().upper()
    if not texto:
        return "", ""
    return texto[0], texto[1:]


def entrada_codigo_segmentado(registry, key_prefix: str = "codigo_segmentado") -> dict:
    """Renderiza a entrada segmentada/completa e retorna o codigo normalizado."""
    modo = st.radio(
        "Modo de entrada do codigo",
        ["Campos segmentados", "Colar codigo completo"],
        horizontal=True,
        key=f"{key_prefix}_modo",
    )

    if modo == "Colar codigo completo":
        codigo_raw = st.text_input(
            "Codigo completo",
            placeholder="Ex: DE-15.25.00.00-6F2-1015",
            key=f"{key_prefix}_codigo_completo",
        )
        codigo = (codigo_raw or "").strip().upper()
        if not codigo:
            return _resultado(modo="completo")

        partes = desmontar_codigo_linha15(codigo, registry)
        if partes is None:
            parsed = registry.parse(codigo)
            mensagem = getattr(parsed, "mensagem", "Codigo invalido.")
            st.error(mensagem)
            return _resultado(codigo=codigo, valido=False, mensagem=mensagem, modo="completo")

        st.caption(
            "Partes reconhecidas: "
            f"Tipo {partes['tipo']} | Linha {partes['linha']} | "
            f"Trecho {partes['trecho']} | Classe {partes['classe']}{partes['subclasse']} | "
            f"Sequencial {partes['sequencial']}"
        )
        st.code(codigo, language=None)
        return _resultado(codigo=codigo, partes=partes, valido=True, modo="completo")

    cols = st.columns([1.2, 0.7, 1.1, 0.9, 0.9, 0.7, 1.0, 1.0])
    with cols[0]:
        tipo = st.selectbox(
            "Tipo",
            options=sorted(LINHA15_TIPOS),
            format_func=_format_tipo,
            key=f"{key_prefix}_tipo",
        )
    with cols[1]:
        linha = st.text_input("Linha", value="15", max_chars=2, key=f"{key_prefix}_linha")
    with cols[2]:
        trecho = st.selectbox(
            "Trecho",
            options=list(LINHA15_TRECHOS),
            format_func=_format_trecho,
            index=list(LINHA15_TRECHOS).index("25"),
            key=f"{key_prefix}_trecho",
        )
    with cols[3]:
        subtrecho = st.text_input("Subtrecho", value="00", max_chars=2, key=f"{key_prefix}_subtrecho")
    with cols[4]:
        unidade = st.text_input("Unidade", value="00", max_chars=2, key=f"{key_prefix}_unidade")
    with cols[5]:
        etapa = st.text_input("Etapa", value="6", max_chars=1, key=f"{key_prefix}_etapa")
    with cols[6]:
        classe_sub = st.text_input("Classe/Subclasse", value="F2", max_chars=3, key=f"{key_prefix}_classe_sub")
    with cols[7]:
        sequencial = st.text_input("Sequencial", placeholder="1015", max_chars=4, key=f"{key_prefix}_sequencial")

    classe, subclasse = _classe_subclasse(classe_sub)
    partes = {
        "tipo": tipo,
        "linha": linha,
        "trecho": trecho,
        "subtrecho": subtrecho,
        "unidade": unidade,
        "etapa": etapa,
        "classe": classe,
        "subclasse": subclasse,
        "sequencial": sequencial,
    }

    try:
        codigo = montar_codigo_segmentado_linha15(partes)
    except ValueError as exc:
        mensagem = str(exc)
        st.warning(mensagem)
        return _resultado(partes=partes, valido=False, mensagem=mensagem)

    parsed = registry.parse(codigo)
    if not getattr(parsed, "valido", False):
        mensagem = getattr(parsed, "mensagem", "Codigo invalido.")
        st.error(mensagem)
        return _resultado(codigo=codigo, partes=partes, valido=False, mensagem=mensagem)

    st.caption("Codigo gerado")
    st.code(codigo, language=None)
    return _resultado(codigo=codigo, partes=partes, valido=True)
