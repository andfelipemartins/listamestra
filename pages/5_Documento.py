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
from core.exporters.excel_exporter import exportar_historico_revisoes
from core.formatacao import fmt_inteiro, fmt_data, disciplina_do_codigo, filtrar_documentos
from core.parsers.registry import ParserRegistry
from app.session import require_contrato, sidebar_contexto
from core.auth.permissions import widget_seletor_perfil, require_permission

_registry = ParserRegistry()


def _trecho_do_codigo(codigo: str) -> str:
    """Deriva o trecho a partir do código documental via parser."""
    try:
        resultado = _registry.parse(codigo)
        if hasattr(resultado, "extras"):
            return resultado.extras.get("trecho", "")
    except Exception:
        pass
    return ""


@st.cache_data(ttl=300)
def _listar_documentos_enriquecidos(contrato_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT d.id, d.codigo, d.titulo, d.tipo, d.trecho,
                   d.modalidade, d.disciplina, d.contrato_id,
                   r.situacao, r.data_emissao
            FROM documentos d
            LEFT JOIN revisoes r
                   ON r.documento_id = d.id AND r.ultima_revisao = 1
            WHERE d.contrato_id = ?
            ORDER BY d.trecho, d.codigo
            """,
            (contrato_id,),
        ).fetchall()
    docs = [dict(r) for r in rows]
    for doc in docs:
        trecho = doc.get("trecho") or ""
        doc["nome_trecho"] = NOME_TRECHO.get(trecho, trecho)
        disc = doc.get("disciplina") or disciplina_do_codigo(doc["codigo"]) or ""
        doc["disciplina_display"] = disc
        doc["disciplina_desc"] = ESTRUTURA.get(disc, "")
        doc["status_atual"] = classificar_status(doc.get("situacao"), doc.get("data_emissao"))
    return docs


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
        trecho = (
            doc.get("trecho")
            or (previsto.get("trecho") if previsto else None)
            or _trecho_do_codigo(doc["codigo"])
            or ""
        )
        if trecho:
            nome_t = NOME_TRECHO.get(trecho, trecho)
            st.markdown(f"**Trecho:** {nome_t} ({trecho})")
        else:
            st.markdown("**Trecho:** —")
        st.markdown(f"**Modalidade:** {doc.get('modalidade') or '—'}")
    with col2:
        disc = (
            doc.get("disciplina")
            or (previsto.get("disciplina") if previsto else None)
            or disciplina_do_codigo(doc["codigo"])
            or ""
        )
        if disc:
            desc_disc = ESTRUTURA.get(disc, "")
            if desc_disc:
                st.markdown(f"**Estrutura:** {disc} — {desc_disc}")
            else:
                st.markdown(f"**Estrutura:** {disc}")
        else:
            st.markdown("**Estrutura:** —")
        st.markdown(f"**Fase:** {fmt_inteiro(doc.get('fase'))}")
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
        data_emissao_fmt = fmt_data(rev.get("data_emissao")) if rev.get("data_emissao") else "sem data"
        with st.expander(f"{emissao} — {data_emissao_fmt} — {status_rev}", expanded=rev.get("ultima_revisao") == 1):
            c1, c2, c3 = st.columns(3)
            with c1:
                label_rev = rev.get("label_revisao") or str(rev.get("revisao") or "—")
                st.markdown(f"**Revisão:** {label_rev}")
                st.markdown(f"**Versão:** {rev.get('versao', '—')}")
                st.markdown(f"**Situação:** {rev.get('situacao') or '—'}")
                st.markdown(f"**Situação Real:** {rev.get('situacao_real') or '—'}")
            with c2:
                st.markdown(f"**Data Elaboração:** {fmt_data(rev.get('data_elaboracao'))}")
                st.markdown(f"**Data Emissão:** {fmt_data(rev.get('data_emissao'))}")
                st.markdown(f"**Data Análise:** {fmt_data(rev.get('data_analise'))}")
                st.markdown(f"**Data Circular:** {fmt_data(rev.get('data_circular'))}")
            with c3:
                st.markdown(f"**Dias Elaboração:** {rev.get('dias_elaboracao') if rev.get('dias_elaboracao') is not None else '—'}")
                st.markdown(f"**Dias Análise:** {rev.get('dias_analise') if rev.get('dias_analise') is not None else '—'}")
                st.markdown(f"**Nº Circular:** {rev.get('emissao_circular') or '—'}")
                st.markdown(f"**Análise Interna:** {fmt_data(rev.get('analise_circular'))}")

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


LIMITE_RESULTADOS = 200


def _exibir_tabela(filtrados: list[dict], busca: str) -> None:
    total = len(filtrados)
    exibir = filtrados[:LIMITE_RESULTADOS]

    if not filtrados:
        if busca.strip():
            st.warning(f'Nenhum documento encontrado para "{busca}".')
        else:
            st.info("Nenhum documento cadastrado neste contrato.")
        return

    if busca.strip():
        legenda = f"{total} resultado(s)."
    else:
        legenda = f"{total} documento(s) no contrato."
    if total > LIMITE_RESULTADOS:
        legenda += f" Mostrando os primeiros {LIMITE_RESULTADOS} — refine a busca para ver mais."
    st.caption(legenda)

    linhas = [
        {
            "Código":    doc["codigo"],
            "Tipo":      doc.get("tipo") or "—",
            "Trecho":    doc.get("nome_trecho") or doc.get("trecho") or "—",
            "Estrutura": doc.get("disciplina_display") or "—",
            "Status":    doc.get("status_atual") or "—",
            "Título":    doc.get("titulo") or "(sem título)",
        }
        for doc in exibir
    ]
    df = pd.DataFrame(linhas)

    event = st.dataframe(
        df,
        key=f"tabela_docs_{busca}",
        use_container_width=True,
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun",
        height=400,
        column_config={
            "Código":    st.column_config.TextColumn("Código",    width="medium"),
            "Tipo":      st.column_config.TextColumn("Tipo",      width="small"),
            "Trecho":    st.column_config.TextColumn("Trecho",    width="medium"),
            "Estrutura": st.column_config.TextColumn("Estrutura", width="small"),
            "Status":    st.column_config.TextColumn("Status",    width="medium"),
            "Título":    st.column_config.TextColumn("Título",    width="large"),
        },
    )

    if event.selection.rows:
        idx = event.selection.rows[0]
        if idx < len(exibir):
            st.session_state["doc_pagina_id"] = exibir[idx]["id"]
    else:
        st.session_state["doc_pagina_id"] = None


# ---------------------------------------------------------------------------
# Página
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Documento — SCLME", page_icon="📄", layout="wide")

widget_seletor_perfil()
contrato = require_contrato()
sidebar_contexto()
require_permission("view_document")

st.title("Pesquisar Documento")

if "doc_pagina_id" not in st.session_state:
    st.session_state["doc_pagina_id"] = None

documentos = _listar_documentos_enriquecidos(contrato["id"])

if not documentos:
    st.info("Nenhum documento cadastrado neste contrato.")
    st.stop()

busca = st.text_input(
    "Buscar documento",
    placeholder="código, título, trecho, estrutura…",
)

filtrados = filtrar_documentos(documentos, busca)
_exibir_tabela(filtrados, busca)

doc_id = st.session_state.get("doc_pagina_id")
if doc_id:
    doc = _carregar_documento(doc_id)
    if doc and doc.get("contrato_id") == contrato["id"]:
        st.divider()
        revisoes = _ficha(doc, contrato["id"])

        with st.sidebar:
            st.markdown("### Exportar")
            nome_arquivo = doc["codigo"].replace("/", "-")
            st.download_button(
                "⬇️ Histórico de revisões (.xlsx)",
                data=exportar_historico_revisoes(revisoes, doc, contrato["nome"]),
                file_name=f"Historico_{nome_arquivo}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

        st.divider()
        _linha_do_tempo(revisoes)
        st.divider()
        _arquivos(doc["id"])
    else:
        st.session_state["doc_pagina_id"] = None
