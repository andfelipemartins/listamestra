"""
pages/5_Documento.py

Detalhe de um documento: ficha técnica, linha do tempo de revisões,
arquivos vinculados e GRDs.
"""

import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db.connection import get_connection
from core.engine.status import STATUS_ORDEM, NOME_TRECHO, classificar_status
from core.engine.disciplinas import ESTRUTURA

# ---------------------------------------------------------------------------
# Acesso a dados
# ---------------------------------------------------------------------------

def _contrato_ativo() -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, nome, cliente FROM contratos WHERE ativo = 1 ORDER BY id LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def _listar_documentos(contrato_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, codigo, titulo, tipo, trecho
            FROM documentos
            WHERE contrato_id = ?
            ORDER BY trecho, codigo
            """,
            (contrato_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _carregar_documento(doc_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM documentos WHERE id = ?",
            (doc_id,),
        ).fetchone()
    return dict(row) if row else None


def _carregar_revisoes(doc_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT r.id, r.revisao, r.versao, r.label_revisao, r.emissao_inicial,
                   r.data_elaboracao, r.data_emissao, r.data_analise,
                   r.dias_elaboracao, r.dias_analise,
                   r.situacao_real, r.situacao, r.retorno,
                   r.emissao_circular, r.analise_circular, r.data_circular,
                   r.ultima_revisao, r.origem, r.criado_em
            FROM revisoes r
            WHERE r.documento_id = ?
            ORDER BY
                CASE WHEN r.data_emissao IS NULL THEN 1 ELSE 0 END,
                r.data_emissao ASC,
                r.revisao ASC,
                r.versao ASC
            """,
            (doc_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _carregar_grds(revisao_ids: list[int]) -> dict[int, list[dict]]:
    if not revisao_ids:
        return {}
    placeholders = ",".join("?" for _ in revisao_ids)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT revisao_id, setor, numero_grd, data_envio
            FROM grds
            WHERE revisao_id IN ({placeholders})
            ORDER BY setor
            """,
            revisao_ids,
        ).fetchall()
    result: dict[int, list[dict]] = {}
    for r in rows:
        result.setdefault(r["revisao_id"], []).append(dict(r))
    return result


def _carregar_arquivos(doc_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT nome_arquivo, extensao, objeto, revisao_detectada,
                   data_modificacao, tamanho_bytes, origem, criado_em
            FROM arquivos
            WHERE documento_id = ?
            ORDER BY nome_arquivo
            """,
            (doc_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _previsto(contrato_id: int, codigo: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT titulo, tipo, disciplina, trecho
            FROM documentos_previstos
            WHERE contrato_id = ? AND codigo = ? AND ativo = 1
            """,
            (contrato_id, codigo),
        ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Componentes de UI
# ---------------------------------------------------------------------------

_STATUS_COLOR = {
    "Em Elaboração": "#95a5a6",
    "Em Análise":    "#3498db",
    "Em Revisão":    "#e67e22",
    "Aprovado":      "#27ae60",
}


def _badge(status: str) -> str:
    cor = _STATUS_COLOR.get(status, "#aaa")
    return (
        f'<span style="background:{cor};color:#fff;padding:2px 10px;'
        f'border-radius:12px;font-size:0.85em;font-weight:600">{status}</span>'
    )


def _ficha(doc: dict, contrato_id: int):
    status_atual = "—"
    revisoes = _carregar_revisoes(doc["id"])
    ultima = next((r for r in revisoes if r["ultima_revisao"]), None)
    if ultima:
        status_atual = classificar_status(ultima.get("situacao"), ultima.get("data_emissao"))

    previsto = _previsto(contrato_id, doc["codigo"])

    st.markdown(
        f"### {doc['codigo']}"
        f"&nbsp;&nbsp;{_badge(status_atual)}",
        unsafe_allow_html=True,
    )
    if doc.get("titulo"):
        st.caption(doc["titulo"])

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"**Tipo:** {doc.get('tipo') or '—'}")
        trecho = doc.get("trecho") or "—"
        nome_t = NOME_TRECHO.get(trecho, trecho)
        st.markdown(f"**Trecho:** {nome_t} ({trecho})")
        st.markdown(f"**Modalidade:** {doc.get('modalidade') or '—'}")
    with col2:
        disc = doc.get("disciplina") or "—"
        desc_disc = ESTRUTURA.get(disc, disc)
        st.markdown(f"**Estrutura:** {disc} — {desc_disc}" if disc != "—" else f"**Estrutura:** —")
        st.markdown(f"**Fase:** {doc.get('fase') or '—'}")
        st.markdown(f"**Responsável:** {doc.get('responsavel') or '—'}")
    with col3:
        st.markdown(f"**Previsto no ID:** {'Sim' if previsto else 'Não'}")
        st.markdown(f"**Origem:** {doc.get('origem') or '—'}")
        criado = (doc.get("criado_em") or "")[:16].replace("T", " ")
        st.markdown(f"**Registrado em:** {criado or '—'}")

    return revisoes


def _linha_do_tempo(revisoes: list[dict]):
    if not revisoes:
        st.info("Nenhuma revisão registrada.")
        return

    st.subheader("Linha do tempo de revisões")

    grds_por_rev = _carregar_grds([r["id"] for r in revisoes])

    for rev in revisoes:
        emissao = rev.get("emissao_inicial") or f"Rev{rev.get('revisao', '?')}"
        status_rev = classificar_status(rev.get("situacao"), rev.get("data_emissao"))
        cor = _STATUS_COLOR.get(status_rev, "#aaa")

        label_header = (
            f"**{emissao}**"
            f"&nbsp;&nbsp;{_badge(status_rev)}"
            f"&nbsp;&nbsp;<small style='color:#888'>{rev.get('data_emissao') or 'sem data'}</small>"
        )
        with st.expander(f"{emissao} — {rev.get('data_emissao') or 'sem data'} — {status_rev}", expanded=rev.get("ultima_revisao") == 1):
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown(f"**Label:** {rev.get('label_revisao') or '—'}")
                st.markdown(f"**Revisão / Versão:** {rev.get('revisao', '—')} / {rev.get('versao', '—')}")
                st.markdown(f"**Situação:** {rev.get('situacao') or '—'}")
                st.markdown(f"**Situação Real:** {rev.get('situacao_real') or '—'}")
            with c2:
                st.markdown(f"**Data Elaboração:** {rev.get('data_elaboracao') or '—'}")
                st.markdown(f"**Data Emissão:** {rev.get('data_emissao') or '—'}")
                st.markdown(f"**Data Análise:** {rev.get('data_analise') or '—'}")
                st.markdown(f"**Data Circular:** {rev.get('data_circular') or '—'}")
            with c3:
                st.markdown(f"**Dias Elaboração:** {rev.get('dias_elaboracao') if rev.get('dias_elaboracao') is not None else '—'}")
                st.markdown(f"**Dias Análise:** {rev.get('dias_analise') if rev.get('dias_analise') is not None else '—'}")
                st.markdown(f"**Nº Circular:** {rev.get('emissao_circular') or '—'}")
                st.markdown(f"**Análise Interna:** {rev.get('analise_circular') or '—'}")

            if rev.get("retorno"):
                st.markdown(f"**Retorno:** {rev['retorno']}")

            grds = grds_por_rev.get(rev["id"], [])
            if grds:
                st.markdown("**GRDs:**")
                for g in grds:
                    setor = g["setor"].capitalize()
                    num = g.get("numero_grd") or "—"
                    data = g.get("data_envio") or "—"
                    st.markdown(f"- {setor}: GRD {num} · Envio {data}")


def _arquivos(doc_id: int):
    arqs = _carregar_arquivos(doc_id)
    with st.expander(f"Arquivos vinculados ({len(arqs)})"):
        if not arqs:
            st.info("Nenhum arquivo vinculado.")
            return

        df = pd.DataFrame(arqs)
        rename = {
            "nome_arquivo":      "Arquivo",
            "extensao":          "Ext.",
            "objeto":            "Objeto",
            "revisao_detectada": "Rev. Detectada",
            "data_modificacao":  "Modificado em",
            "origem":            "Origem",
        }
        cols = [c for c in rename if c in df.columns]
        st.dataframe(
            df[cols].rename(columns=rename),
            use_container_width=True,
            hide_index=True,
        )


# ---------------------------------------------------------------------------
# Página
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Documento — SCLME", page_icon="📄", layout="wide")

contrato = _contrato_ativo()

if contrato is None:
    st.title("📄 Documento")
    st.warning("Nenhum contrato encontrado. Importe os dados na página Importação.")
    st.stop()

st.title("📄 Detalhe do Documento")
st.caption(contrato["nome"])

documentos = _listar_documentos(contrato["id"])

if not documentos:
    st.info("Nenhum documento cadastrado neste contrato.")
    st.stop()

# Busca por código na sidebar
with st.sidebar:
    st.markdown("### Buscar documento")
    busca = st.text_input("Código ou título", placeholder="DE-15.25...")

opcoes = documentos
if busca.strip():
    termo = busca.strip().lower()
    opcoes = [
        d for d in documentos
        if termo in d["codigo"].lower() or termo in (d.get("titulo") or "").lower()
    ]

if not opcoes:
    st.warning(f"Nenhum documento encontrado para: **{busca}**")
    st.stop()

# Selectbox com código + título
labels = [
    f"{d['codigo']}  —  {d.get('titulo') or '(sem título)'}"
    for d in opcoes
]
escolha = st.selectbox("Documento", labels, label_visibility="collapsed")
idx = labels.index(escolha)
doc_selecionado = opcoes[idx]

doc = _carregar_documento(doc_selecionado["id"])
st.divider()

revisoes = _ficha(doc, contrato["id"])
st.divider()

_linha_do_tempo(revisoes)
st.divider()

_arquivos(doc["id"])
