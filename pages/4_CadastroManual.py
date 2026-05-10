"""
pages/4_CadastroManual.py

Cadastro manual de documentos e revisões.
Aceita um ou vários códigos colados de uma vez (um por linha).
"""

import os
import sys
from datetime import date
from typing import Optional

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.parsers.registry import ParserRegistry
from core.parsers.codigo_builder import parsear_lista_codigos
from core.importers.cadastro_importer import salvar_documento_revisao
from core.engine.disciplinas import (
    ESTRUTURA_OPCOES,
    MODALIDADES,
    SITUACOES,
    codigo_para_opcao,
    opcao_para_codigo,
)
from app.session import require_contrato, sidebar_contexto
from core.auth.permissions import require_permission, widget_seletor_perfil
from db.connection import get_connection

st.set_page_config(
    page_title="Cadastro Manual — SCLME",
    page_icon="📝",
    layout="wide",
)

widget_seletor_perfil()
sidebar_contexto()

st.title("📝 Cadastro Manual")
st.caption(
    "Registre documentos e revisões individualmente — "
    "complementa as importações em lote via Excel."
)

contrato = require_contrato()
require_permission("create_document")

_registry = ParserRegistry()

st.caption(f"Contrato: **{contrato['nome']}**")
st.divider()

# ---------------------------------------------------------------------------
# Acesso a dados
# ---------------------------------------------------------------------------

def _buscar_documento(contrato_id: int, codigo: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM documentos WHERE contrato_id = ? AND codigo = ?",
            (contrato_id, codigo),
        ).fetchone()
    return dict(row) if row else None


def _listar_revisoes(documento_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT label_revisao, versao, emissao_inicial, data_emissao, situacao
            FROM revisoes
            WHERE documento_id = ?
            ORDER BY
                CASE WHEN data_emissao IS NULL THEN 1 ELSE 0 END,
                data_emissao ASC, revisao ASC, versao ASC
            """,
            (documento_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Helpers de formulário
# ---------------------------------------------------------------------------

def _ks(codigo: str) -> str:
    """Converte código em string segura para usar em keys do Streamlit."""
    return codigo.replace("-", "_").replace(".", "_")


def _secao_documento_form(codigo: str, existing: Optional[dict]) -> None:
    ks = _ks(codigo)
    c1, c2 = st.columns(2)
    with c1:
        st.text_input(
            "Descrição / Objeto *",
            value=existing.get("titulo") or "" if existing else "",
            key=f"cm_titulo_{ks}",
        )
    with c2:
        st.text_input(
            "Elaboração (responsável)",
            value=existing.get("responsavel") or "" if existing else "",
            key=f"cm_responsavel_{ks}",
        )

    c3, c4, c5 = st.columns(3)
    with c3:
        modalidade_val = existing.get("modalidade") or "" if existing else ""
        modalidade_idx = MODALIDADES.index(modalidade_val) if modalidade_val in MODALIDADES else None
        st.selectbox("Modalidade", options=MODALIDADES, index=modalidade_idx, key=f"cm_modalidade_{ks}")
    with c4:
        disciplina_val = existing.get("disciplina") or "" if existing else ""
        opcao_atual = codigo_para_opcao(disciplina_val)
        estrutura_idx = (
            ESTRUTURA_OPCOES.index(opcao_atual)
            if opcao_atual and opcao_atual in ESTRUTURA_OPCOES
            else None
        )
        st.selectbox(
            "Estrutura (disciplina)", options=ESTRUTURA_OPCOES,
            index=estrutura_idx, key=f"cm_estrutura_{ks}",
        )
    with c5:
        st.text_input(
            "Fase",
            value=existing.get("fase") or "" if existing else "",
            key=f"cm_fase_{ks}",
            placeholder="Ex: EXECUTIVO",
        )


def _secao_revisao_form(codigo: str) -> None:
    ks = _ks(codigo)

    c1, c2 = st.columns(2)
    with c1:
        st.text_input("Revisão *", key=f"cm_revisao_{ks}", placeholder="Ex: 0, 1, A, A1")
    with c2:
        st.number_input("Versão *", min_value=1, value=1, step=1, key=f"cm_versao_{ks}")

    c3, c4, c5 = st.columns(3)
    with c3:
        st.date_input("Data Elaboração", value=None, key=f"cm_data_elab_{ks}", format="DD/MM/YYYY")
    with c4:
        st.date_input("Data Emissão", value=None, key=f"cm_data_emis_{ks}", format="DD/MM/YYYY")
    with c5:
        st.date_input("Data Análise", value=None, key=f"cm_data_anal_{ks}", format="DD/MM/YYYY")

    c6, c7 = st.columns(2)
    with c6:
        st.selectbox("Situação", options=[""] + SITUACOES, index=0, key=f"cm_situacao_{ks}")
    with c7:
        st.text_input("Situação Real", key=f"cm_situacao_real_{ks}", placeholder="Ex: NÃO APROVADO")

    c8, c9, c10 = st.columns(3)
    with c8:
        st.text_input("Análise Interna", key=f"cm_analise_interna_{ks}", placeholder="Ex: AI-001")
    with c9:
        st.date_input("Data Circular", value=None, key=f"cm_data_circular_{ks}", format="DD/MM/YYYY")
    with c10:
        st.text_input("Nº Circular", key=f"cm_num_circular_{ks}", placeholder="Ex: 558/2024")


def _secao_grds_form(codigo: str) -> None:
    ks = _ks(codigo)
    setores = [("producao", "Produção"), ("topografia", "Topografia"), ("qualidade", "Qualidade")]
    cols = st.columns(len(setores))
    for col, (setor, nome) in zip(cols, setores):
        with col:
            st.markdown(f"*{nome}*")
            st.text_input(f"Nº GRD", key=f"cm_grd_num_{setor}_{ks}", placeholder="Ex: GRD-001")
            st.date_input("Data Envio", value=None, key=f"cm_grd_data_{setor}_{ks}", format="DD/MM/YYYY")


def _iso(val) -> Optional[str]:
    if val is None:
        return None
    if hasattr(val, "isoformat") and val != date(1900, 1, 1):
        return val.isoformat()
    return None


def _ler_doc_fields(codigo: str) -> dict:
    ks = _ks(codigo)
    return {
        "titulo":      st.session_state.get(f"cm_titulo_{ks}", ""),
        "responsavel": st.session_state.get(f"cm_responsavel_{ks}", ""),
        "modalidade":  st.session_state.get(f"cm_modalidade_{ks}", ""),
        "disciplina":  opcao_para_codigo(st.session_state.get(f"cm_estrutura_{ks}", "") or ""),
        "fase":        st.session_state.get(f"cm_fase_{ks}", ""),
    }


def _ler_rev_fields(codigo: str) -> dict:
    ks = _ks(codigo)
    return {
        "label_revisao":   str(st.session_state.get(f"cm_revisao_{ks}", "") or "").strip(),
        "versao":          int(st.session_state.get(f"cm_versao_{ks}", 1) or 1),
        "data_elaboracao": _iso(st.session_state.get(f"cm_data_elab_{ks}")),
        "data_emissao":    _iso(st.session_state.get(f"cm_data_emis_{ks}")),
        "data_analise":    _iso(st.session_state.get(f"cm_data_anal_{ks}")),
        "situacao":        st.session_state.get(f"cm_situacao_{ks}") or None,
        "situacao_real":   (st.session_state.get(f"cm_situacao_real_{ks}") or "").strip() or None,
        "analise_interna": (st.session_state.get(f"cm_analise_interna_{ks}") or "").strip() or None,
        "data_circular":   _iso(st.session_state.get(f"cm_data_circular_{ks}")),
        "num_circular":    (st.session_state.get(f"cm_num_circular_{ks}") or "").strip() or None,
    }


def _ler_grds(codigo: str) -> list[dict]:
    ks = _ks(codigo)
    grds = []
    for setor in ("producao", "topografia", "qualidade"):
        num  = (st.session_state.get(f"cm_grd_num_{setor}_{ks}") or "").strip() or None
        data = _iso(st.session_state.get(f"cm_grd_data_{setor}_{ks}"))
        grds.append({"setor": setor, "numero_grd": num, "data_envio": data})
    return grds


def _limpar_estado_form():
    for k in list(st.session_state.keys()):
        if k.startswith("cm_") and k != "cm_texto_codigos":
            del st.session_state[k]


# ---------------------------------------------------------------------------
# Fase 1 — entrada de códigos
# ---------------------------------------------------------------------------

st.text_area(
    "Códigos dos documentos",
    placeholder=(
        "Cole um ou mais códigos, um por linha:\n\n"
        "DE-15.25.00.00-6F2-1001\n"
        "DE-15.25.00.00-6F2-1002\n"
        "DE-15.25.00.00-6F2-1003"
    ),
    height=130,
    key="cm_texto_codigos",
)

analisar = st.button("Analisar Códigos", type="primary")

if analisar:
    texto = (st.session_state.get("cm_texto_codigos") or "").strip()
    if not texto:
        st.warning("Cole pelo menos um código para continuar.")
        st.stop()
    validos, invalidos = parsear_lista_codigos(texto, _registry)
    _limpar_estado_form()
    st.session_state["cm_validos"]   = validos
    st.session_state["cm_invalidos"] = invalidos
    st.session_state["cm_analisado"] = True
    st.rerun()

# ---------------------------------------------------------------------------
# Fase 2 — formulário de cadastro
# ---------------------------------------------------------------------------

if not st.session_state.get("cm_analisado"):
    st.stop()

validos   = st.session_state.get("cm_validos", [])
invalidos = st.session_state.get("cm_invalidos", [])

if invalidos:
    for codigo, erro in invalidos:
        st.error(f"❌ `{codigo}` — {erro.mensagem}")
    st.warning("Corrija os códigos inválidos no campo acima e clique em Analisar novamente.")
    st.stop()

if not validos:
    st.info("Nenhum código válido encontrado.")
    st.stop()

n = len(validos)
label_btn = f"Salvar {n} documento(s)" if n > 1 else "Salvar documento"
st.info(f"{n} código(s) válido(s) reconhecido(s).")

with st.form("form_lote"):
    for codigo, parsed in validos:
        existing = _buscar_documento(contrato["id"], codigo)
        trecho   = parsed.extras.get("nome_trecho", "—")
        header   = f"📄 {codigo} — {parsed.tipo} | {trecho}"
        if existing:
            revisoes_ex = _listar_revisoes(existing["id"])
            header += f" *(já existe — {len(revisoes_ex)} revisão(ões))*"

        with st.expander(header, expanded=True):
            st.markdown("**Dados do Documento**")
            _secao_documento_form(codigo, existing)

            st.divider()
            st.markdown("**Dados da Revisão**")
            _secao_revisao_form(codigo)

            st.divider()
            st.markdown("**GRD — opcional**")
            _secao_grds_form(codigo)

    st.markdown("")
    submitted = st.form_submit_button(label_btn, type="primary", use_container_width=True)

if submitted:
    erros = []
    for codigo, _ in validos:
        doc = _ler_doc_fields(codigo)
        rev = _ler_rev_fields(codigo)
        if not doc["titulo"].strip():
            erros.append(f"`{codigo}`: Descrição / Objeto é obrigatório.")
        if not rev["label_revisao"]:
            erros.append(f"`{codigo}`: Revisão é obrigatória.")

    if erros:
        for e in erros:
            st.error(e)
    else:
        resultados = []
        for codigo, _ in validos:
            msg = salvar_documento_revisao(
                contrato["id"],
                codigo,
                _ler_doc_fields(codigo),
                _ler_rev_fields(codigo),
                _ler_grds(codigo),
            )
            resultados.append((codigo, msg))

        for codigo, msg in resultados:
            if "sucesso" in msg.lower():
                st.success(f"**{codigo}**: {msg}")
            else:
                st.warning(f"**{codigo}**: {msg}")

        if st.button("Cadastrar novos documentos", key="btn_novo_lote"):
            _limpar_estado_form()
            st.session_state.pop("cm_validos", None)
            st.session_state.pop("cm_invalidos", None)
            st.session_state.pop("cm_analisado", None)
            st.rerun()
