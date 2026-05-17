"""
pages/4_CadastroManual.py

Cadastro manual de documentos e revisões.
Aceita um ou vários códigos colados de uma vez (um por linha).
A lista é acumulativa: novos códigos são adicionados sem apagar os anteriores.
"""

import os
import sys
from datetime import date
from typing import Optional

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.parsers.registry import ParserRegistry
from core.parsers.codigo_builder import parsear_lista_codigos, mesclar_codigos
from core.engine.disciplinas import MODALIDADES, SITUACOES
from core.services.cadastro_service import CadastroService
from app.session import require_contrato, sidebar_contexto
from core.auth.permissions import require_permission, widget_seletor_perfil

st.set_page_config(
    page_title="Cadastro Manual — SCLME",
    page_icon="📝",
    layout="wide",
)

widget_seletor_perfil()
sidebar_contexto()

st.title("Cadastrar")

contrato = require_contrato()
require_permission("create_document")

_registry = ParserRegistry()
_service = CadastroService(parser_registry=_registry)

st.caption(f"Contrato: **{contrato['nome']}**")
st.divider()


# ---------------------------------------------------------------------------
# Helpers de formulário
# ---------------------------------------------------------------------------

def _ks(codigo: str) -> str:
    return codigo.replace("-", "_").replace(".", "_")


def _iso(val) -> Optional[str]:
    if val is None:
        return None
    if hasattr(val, "isoformat") and val != date(1900, 1, 1):
        return val.isoformat()
    return None


def _secao_documento(codigo: str, existing: Optional[dict]) -> None:
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

    modalidade_val = existing.get("modalidade") or "" if existing else ""
    modalidade_idx = MODALIDADES.index(modalidade_val) if modalidade_val in MODALIDADES else None
    st.selectbox("Modalidade", options=MODALIDADES, index=modalidade_idx, key=f"cm_modalidade_{ks}")


def _secao_revisao(codigo: str) -> None:
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


def _secao_grds(codigo: str) -> None:
    ks = _ks(codigo)
    setores = [("producao", "Produção"), ("topografia", "Topografia"), ("qualidade", "Qualidade")]
    cols = st.columns(len(setores))
    for col, (setor, nome) in zip(cols, setores):
        with col:
            st.markdown(f"*{nome}*")
            st.text_input(f"Nº GRD", key=f"cm_grd_num_{setor}_{ks}", placeholder="Ex: GRD-001")
            st.date_input("Data Envio", value=None, key=f"cm_grd_data_{setor}_{ks}", format="DD/MM/YYYY")


def _ler_doc_fields(codigo: str) -> dict:
    ks = _ks(codigo)
    return {
        "titulo":      st.session_state.get(f"cm_titulo_{ks}", ""),
        "responsavel": st.session_state.get(f"cm_responsavel_{ks}", ""),
        "modalidade":  st.session_state.get(f"cm_modalidade_{ks}", ""),
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


def _campos_obrigatorios_preenchidos(validos: list) -> bool:
    for codigo, _ in validos:
        ks = _ks(codigo)
        titulo  = (st.session_state.get(f"cm_titulo_{ks}") or "").strip()
        revisao = (st.session_state.get(f"cm_revisao_{ks}") or "").strip()
        if not titulo or not revisao:
            return False
    return True


def _limpar_codigo(codigo: str) -> None:
    """Remove todos os campos de session_state do documento indicado."""
    suffix = f"_{_ks(codigo)}"
    for k in list(st.session_state.keys()):
        if k.startswith("cm_") and k.endswith(suffix):
            del st.session_state[k]


def _limpar_lista() -> None:
    """Limpa a lista de documentos em edição; mantém apenas a caixa de texto."""
    for k in list(st.session_state.keys()):
        if k.startswith("cm_") and k != "cm_texto_codigos":
            del st.session_state[k]


def _limpar_tudo() -> None:
    """Limpa todo o estado do formulário (usado em Cadastrar novos)."""
    for k in list(st.session_state.keys()):
        if k.startswith("cm_"):
            del st.session_state[k]


# ---------------------------------------------------------------------------
# Entrada de códigos — caixa + botão (acumulativo)
# ---------------------------------------------------------------------------

# Key versionada: incrementar a versão no rerun cria um novo widget vazio,
# contornando a restrição do Streamlit de não permitir modificar session_state
# de um widget já instanciado no mesmo ciclo.
_ver     = st.session_state.get("cm_input_version", 0)
_txt_key = f"cm_texto_codigos_{_ver}"

st.text_area(
    "Códigos dos documentos",
    placeholder=(
        "Cole um ou mais códigos, um por linha:\n\n"
        "DE-15.25.00.00-6F2-1001\n"
        "DE-15.25.00.00-6F2-1002\n"
        "DE-15.25.00.00-6F2-1003"
    ),
    height=130,
    key=_txt_key,
)

analisar = st.button("Analisar Códigos", type="primary")

if analisar:
    texto = (st.session_state.get(_txt_key) or "").strip()
    if not texto:
        st.warning("Cole pelo menos um código para continuar.")
        st.stop()

    novos_validos, invalidos_batch = parsear_lista_codigos(texto, _registry)
    existentes = st.session_state.get("cm_validos", [])
    merged, duplicatas = mesclar_codigos(novos_validos, existentes)

    st.session_state["cm_validos"]         = merged
    st.session_state["cm_invalidos_batch"] = invalidos_batch
    st.session_state["cm_duplicatas"]      = duplicatas
    st.session_state["cm_input_version"]   = _ver + 1   # nova key → caixa vazia no próximo render
    st.rerun()

# ---------------------------------------------------------------------------
# Pós-salvamento — mostra resultados e botão de reset
# ---------------------------------------------------------------------------

if st.session_state.get("cm_salvo"):
    for codigo, msg in st.session_state.get("cm_resultados", []):
        if "sucesso" in msg.lower():
            st.success(f"**{codigo}**: {msg}")
        else:
            st.warning(f"**{codigo}**: {msg}")

    if st.button("Cadastrar novos documentos", type="primary"):
        _limpar_tudo()
        st.rerun()

    st.stop()

# ---------------------------------------------------------------------------
# Feedback do último lote de análise
# ---------------------------------------------------------------------------

invalidos_batch = st.session_state.get("cm_invalidos_batch", [])
for codigo, erro in invalidos_batch:
    st.error(f"❌ `{codigo}` — {erro.mensagem}")

duplicatas = st.session_state.get("cm_duplicatas", 0)
if duplicatas:
    st.warning(
        f"{duplicatas} código(s) já estavam na lista e foram ignorados."
    )

# ---------------------------------------------------------------------------
# Lista acumulada de documentos
# ---------------------------------------------------------------------------

validos = st.session_state.get("cm_validos", [])

if not validos:
    st.stop()

n = len(validos)

col_info, col_limpar = st.columns([5, 1])
with col_info:
    st.info(f"{n} código(s) na lista.")
with col_limpar:
    if st.button("Limpar lista", use_container_width=True):
        _limpar_lista()
        st.rerun()

st.divider()

# Renderiza campos por código (sem st.form — session_state atualiza a cada interação,
# permitindo checar campos obrigatórios em tempo real para habilitar/desabilitar o botão)
for codigo, parsed in list(validos):
    ks       = _ks(codigo)
    existing = _service.buscar_documento_existente(contrato["id"], codigo)
    trecho   = parsed.extras.get("nome_trecho", "—")
    header   = f"📄 {codigo} — {parsed.tipo} | {trecho}"
    if existing:
        revisoes_ex = _service.listar_revisoes_existentes(existing["id"])
        header += f" *(já existe — {len(revisoes_ex)} revisão(ões))*"

    # Botão de remoção fica fora do expander, sempre visível à direita do cabeçalho
    col_exp, col_rem = st.columns([20, 1])
    with col_rem:
        if st.button("✕", key=f"cm_btn_remover_{ks}", help="Remover este documento da lista"):
            _limpar_codigo(codigo)
            st.session_state["cm_validos"] = [
                (c, p) for c, p in validos if c != codigo
            ]
            st.rerun()
    with col_exp:
        with st.expander(header, expanded=False):
            e = parsed.extras
            st.caption(
                f"**{parsed.tipo}** — {parsed.descricao_tipo} · "
                f"Trecho: **{e.get('nome_trecho', '—')}** · "
                f"Etapa: **{e.get('etapa', '—')}** · "
                f"Disciplina: **{e.get('classe', '')}{e.get('subclasse', '')}**"
            )

            st.markdown("**Dados do Documento**")
            _secao_documento(codigo, existing)

            st.divider()
            st.markdown("**Dados da Revisão**")
            _secao_revisao(codigo)

            st.divider()
            st.markdown("**GRD — opcional**")
            _secao_grds(codigo)

# ---------------------------------------------------------------------------
# Botão de salvamento
# ---------------------------------------------------------------------------

pode_salvar = _campos_obrigatorios_preenchidos(validos)
label_btn   = f"Salvar {n} documento(s)" if n > 1 else "Salvar documento"

if not pode_salvar:
    st.caption("⚠️ Preencha Descrição/Objeto e Revisão em todos os documentos para habilitar o salvamento.")

salvar = st.button(label_btn, type="primary", disabled=not pode_salvar, use_container_width=True)

if salvar:
    resultados = []
    for codigo, _ in validos:
        resultado = _service.cadastrar_documento_manual(
            contrato["id"],
            codigo,
            _ler_doc_fields(codigo),
            _ler_rev_fields(codigo),
            _ler_grds(codigo),
        )
        resultados.append((codigo, resultado.mensagem))

    st.session_state["cm_resultados"] = resultados
    st.session_state["cm_salvo"]      = True
    st.rerun()
