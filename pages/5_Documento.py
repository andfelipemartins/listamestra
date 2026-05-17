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
from core.formatacao import fmt_inteiro, fmt_data, filtrar_documentos
from core.repositories.documento_repository import DocumentoRepository
from core.repositories.revisao_repository import RevisaoRepository
from core.services.documento_service import DocumentoService
from app.session import require_contrato, sidebar_contexto
from core.auth.permissions import widget_seletor_perfil, require_permission

_documento_repository = DocumentoRepository()
_revisao_repository = RevisaoRepository()
_service = DocumentoService(_documento_repository, _revisao_repository)


@st.cache_data(ttl=300)
def _listar_documentos_enriquecidos(contrato_id: int) -> list[dict]:
    return _service.listar_documentos_enriquecidos(contrato_id)


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


def _ficha(doc: dict, revisoes: list[dict], status_atual: str, previsto: dict | None):
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
        trecho_display = _service.obter_trecho_exibicao(doc, previsto)
        if trecho_display:
            st.markdown(f"**Trecho:** {trecho_display}")
        else:
            st.markdown("**Trecho:** —")
        st.markdown(f"**Modalidade:** {doc.get('modalidade') or '—'}")
    with col2:
        disc_display = _service.obter_disciplina_exibicao(doc, previsto)
        if disc_display:
            st.markdown(f"**Estrutura:** {disc_display}")
        else:
            st.markdown("**Estrutura:** —")
        st.markdown(f"**Fase:** {fmt_inteiro(doc.get('fase'))}")
        st.markdown(f"**Responsável:** {doc.get('responsavel') or '—'}")
    with col3:
        st.markdown(f"**Previsto no ID:** {'Sim' if previsto else 'Não'}")
        st.markdown(f"**Origem:** {doc.get('origem') or '—'}")
        criado = (doc.get("criado_em") or "")[:16].replace("T", " ")
        st.markdown(f"**Registrado em:** {criado or '—'}")


def _linha_do_tempo(revisoes: list[dict]):
    if not revisoes:
        st.info("Nenhuma revisão registrada.")
        return

    st.subheader("Linha do tempo de revisões")

    grds_por_rev = _carregar_grds([r["id"] for r in revisoes])

    for rev in revisoes:
        emissao = rev.get("emissao_inicial") or f"Rev{rev.get('revisao', '?')}"
        status_rev = classificar_status(rev.get("situacao"), rev.get("data_emissao"))

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

    resumos = [_service.montar_resumo_documento(doc) for doc in exibir]
    df = pd.DataFrame(
        [
            {
                "Código":    r["codigo"],
                "Tipo":      r["tipo"],
                "Trecho":    r["nome_trecho"],
                "Estrutura": r["disciplina_display"],
                "Status":    r["status_atual"],
                "Título":    r["titulo"],
            }
            for r in resumos
        ]
    )

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
    detalhe = _service.carregar_detalhe_documento(doc_id)
    if detalhe and detalhe["documento"].get("contrato_id") == contrato["id"]:
        doc = detalhe["documento"]
        revisoes = detalhe["revisoes"]
        previsto = _service.buscar_previsto(contrato["id"], doc["codigo"])

        st.divider()
        _ficha(doc, revisoes, detalhe["status_atual"], previsto)

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
