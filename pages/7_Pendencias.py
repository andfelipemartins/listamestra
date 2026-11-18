"""Central operacional para consultar e tratar pendências do contrato."""

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.session import require_contrato, sidebar_contexto
from core.auth.permissions import can, require_permission, widget_seletor_perfil
from core.services.pendencias_service import PendenciasService

st.set_page_config(page_title="Pendências — SCLME", page_icon="⚠️", layout="wide")

widget_seletor_perfil()
contrato = require_contrato()
sidebar_contexto()
require_permission("view_dashboard")

_service = PendenciasService()
_rotulos = _service.rotulos_por_categoria()

st.title("CENTRAL DE PENDÊNCIAS")
st.caption(f"Contrato: **{contrato['nome']}**")

feedback = st.session_state.pop("_pendencias_feedback", None)
if feedback:
    st.success(feedback)

resumo = _service.resumo_por_categoria(contrato["id"])
st.subheader("Resumo por categoria")
_colunas_resumo = 4
for _inicio in range(0, len(_rotulos), _colunas_resumo):
    _grupo = list(_rotulos.items())[_inicio : _inicio + _colunas_resumo]
    for _coluna, (_tipo, _rotulo) in zip(st.columns(_colunas_resumo), _grupo):
        with _coluna:
            with st.container(border=True):
                _total = resumo.get(_tipo, 0)
                if _total:
                    st.metric(_rotulo, _total)
                else:
                    st.caption(_rotulo)
                    st.caption("0 pendências")

_opcoes = _service.opcoes_filtros(contrato["id"])
st.subheader("Filtros")
_filtro_tipo, _filtro_trecho, _filtro_disciplina, _filtro_dispensadas = st.columns(4)
with _filtro_tipo:
    _tipo_selecionado = st.selectbox(
        "Tipo de pendência",
        options=["", *_rotulos.keys()],
        format_func=lambda tipo: "Todas as categorias" if not tipo else _rotulos[tipo],
        key="pendencias_filtro_tipo",
    )
with _filtro_trecho:
    _trecho_selecionado = st.selectbox(
        "Trecho",
        options=["", *_opcoes["trechos"]],
        format_func=lambda trecho: trecho or "Todos os trechos",
        key="pendencias_filtro_trecho",
    )
with _filtro_disciplina:
    _disciplina_selecionada = st.selectbox(
        "Disciplina",
        options=["", *_opcoes["disciplinas"]],
        format_func=lambda disciplina: disciplina or "Todas as disciplinas",
        key="pendencias_filtro_disciplina",
    )
with _filtro_dispensadas:
    _incluir_dispensadas = st.toggle(
        "Mostrar dispensadas",
        value=False,
        key="pendencias_incluir_dispensadas",
    )

_pendencias = _service.listar_pendencias(
    contrato["id"],
    incluir_dispensadas=_incluir_dispensadas,
    tipo=_tipo_selecionado or None,
    trecho=_trecho_selecionado or None,
    disciplina=_disciplina_selecionada or None,
)
_por_categoria = {tipo: [] for tipo in _rotulos}
for _pendencia in _pendencias:
    _por_categoria[_pendencia["tipo"]].append(_pendencia)

st.subheader("Pendências")
if not _pendencias:
    st.info("Nenhuma pendência corresponde aos filtros selecionados.")

for _tipo, _itens in _por_categoria.items():
    if not _itens:
        continue
    with st.expander(f"{_rotulos[_tipo]} ({len(_itens)})"):
        for _indice, _item in enumerate(_itens):
            _chave_widget = f"{_item['tipo']}_{_item['chave']}_{_indice}"
            with st.container(border=True):
                _codigo = _item.get("codigo")
                if _codigo:
                    st.markdown(f"**{_codigo}**")
                else:
                    st.markdown(f"**{_rotulos[_tipo]} — {_item['chave']}**")
                if _item.get("titulo"):
                    st.write(_item["titulo"])
                if _item.get("mensagem"):
                    st.write(_item["mensagem"])
                _localizacao = []
                if _item.get("trecho"):
                    _localizacao.append(f"Trecho {_item['trecho']}")
                if _item.get("disciplina"):
                    _localizacao.append(f"Disciplina {_item['disciplina']}")
                if _localizacao:
                    st.caption(" · ".join(_localizacao))

                if _item.get("documento_id") is not None:
                    if st.button(
                        "Abrir documento",
                        key=f"pend_doc_{_chave_widget}",
                    ):
                        st.session_state["doc_pagina_id"] = int(_item["documento_id"])
                        st.switch_page("pages/5_Documento.py")

                if _item["dispensada"]:
                    _acao = {
                        "resolvida": "Resolvida",
                        "ignorada": "Ignorada",
                    }.get(_item["acao_dispensa"], _item["acao_dispensa"])
                    _data = _item.get("dispensada_em") or "data não disponível"
                    st.caption(f"{_acao} em {_data}")
                    st.write(_item.get("observacao_dispensa") or "Sem observação registrada.")
                    if can("manage_pendencias"):
                        if st.button("Reativar", key=f"pend_reativar_{_chave_widget}"):
                            _service.reativar_pendencia(
                                contrato["id"],
                                _item["dispensa_id"],
                            )
                            st.session_state["_pendencias_feedback"] = "Pendência reativada."
                            st.rerun()
                elif can("manage_pendencias"):
                    _observacao = st.text_input(
                        "Observação (opcional)",
                        key=f"pend_obs_{_chave_widget}",
                    )
                    _botao_resolvida, _botao_ignorar = st.columns(2)
                    with _botao_resolvida:
                        if st.button("Resolvida", key=f"pend_resolvida_{_chave_widget}"):
                            _service.dispensar_pendencia(
                                contrato["id"],
                                _item["tipo"],
                                _item["chave"],
                                "resolvida",
                                _observacao.strip() or None,
                                st.session_state.get("perfil", "admin"),
                            )
                            st.session_state["_pendencias_feedback"] = "Pendência marcada como resolvida."
                            st.rerun()
                    with _botao_ignorar:
                        if st.button("Ignorar", key=f"pend_ignorar_{_chave_widget}"):
                            _service.dispensar_pendencia(
                                contrato["id"],
                                _item["tipo"],
                                _item["chave"],
                                "ignorada",
                                _observacao.strip() or None,
                                st.session_state.get("perfil", "admin"),
                            )
                            st.session_state["_pendencias_feedback"] = "Pendência ignorada."
                            st.rerun()
