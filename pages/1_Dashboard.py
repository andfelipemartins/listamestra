"""
pages/1_Dashboard.py

Dashboard principal do SCLME.
Exibe progresso por status e por trecho para o contrato ativo.
"""

import os
import sys

import plotly.express as px
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db.connection import get_connection
from core.engine.status import (
    STATUS_ORDEM,
    NOME_TRECHO,
    carregar_progresso,
)

STATUS_COR = {
    "Em Elaboração": "#95a5a6",
    "Em Análise":    "#3498db",
    "Em Revisão":    "#e67e22",
    "Aprovado":      "#27ae60",
}

# ---------------------------------------------------------------------------
# Acesso a dados
# ---------------------------------------------------------------------------

def _contrato_ativo():
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, nome, cliente FROM contratos WHERE ativo = 1 ORDER BY id LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def _ultima_importacao(contrato_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT origem, arquivo_importado, total_registros, total_novos,
                   total_atualizados, total_erros, confirmado_em
            FROM importacoes
            WHERE contrato_id = ? AND status = 'concluido'
            ORDER BY id DESC LIMIT 1
            """,
            (contrato_id,),
        ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Componentes de UI
# ---------------------------------------------------------------------------

def _kpis(df: pd.DataFrame):
    total = len(df)
    counts = df["status"].value_counts()

    c0, c1, c2, c3, c4 = st.columns(5)
    c0.metric("Total Previstos", total)
    for col, status in zip([c1, c2, c3, c4], STATUS_ORDEM):
        n = int(counts.get(status, 0))
        pct = n / total * 100 if total else 0
        col.metric(status, n, f"{pct:.1f}%")


def _barra_progresso(df: pd.DataFrame):
    total = len(df)
    aprovados = int((df["status"] == "Aprovado").sum())
    pct = aprovados / total * 100 if total else 0
    st.markdown(f"#### Progresso geral: **{pct:.1f}%** aprovado &nbsp;({aprovados} / {total})")
    st.progress(pct / 100)


def _grafico_geral(df: pd.DataFrame):
    contagem = (
        df.groupby(["nome_trecho", "status"])
        .size()
        .reset_index(name="qtd")
    )
    # Garante que todos os status aparecem em todos os trechos (mesmo com qtd=0)
    trechos = contagem["nome_trecho"].unique().tolist()
    completo = pd.MultiIndex.from_product(
        [trechos, STATUS_ORDEM], names=["nome_trecho", "status"]
    )
    contagem = (
        contagem.set_index(["nome_trecho", "status"])
        .reindex(completo, fill_value=0)
        .reset_index()
    )

    fig = px.bar(
        contagem,
        x="nome_trecho",
        y="qtd",
        color="status",
        color_discrete_map=STATUS_COR,
        category_orders={"status": STATUS_ORDEM},
        barmode="stack",
        title="Documentos por Trecho e Status",
        labels={"nome_trecho": "Trecho", "qtd": "Documentos", "status": "Status"},
    )
    fig.update_layout(legend_title_text="Status", xaxis_title="")
    st.plotly_chart(fig, use_container_width=True)


def _detalhe_por_trecho(df: pd.DataFrame):
    trechos_presentes = sorted(df["trecho"].unique())
    nomes = [NOME_TRECHO.get(t, t) for t in trechos_presentes]
    tabs = st.tabs(nomes)

    for tab, trecho in zip(tabs, trechos_presentes):
        with tab:
            df_t = df[df["trecho"] == trecho]
            total_t = len(df_t)
            counts_t = df_t["status"].value_counts()
            aprovados_t = int(counts_t.get("Aprovado", 0))
            pct_t = aprovados_t / total_t * 100 if total_t else 0

            c1, c2, c3, c4 = st.columns(4)
            for col, status in zip([c1, c2, c3, c4], STATUS_ORDEM):
                n = int(counts_t.get(status, 0))
                col.metric(status, n, f"{n/total_t*100:.1f}%" if total_t else "—")

            st.progress(pct_t / 100, text=f"{pct_t:.1f}% aprovado  ({aprovados_t}/{total_t})")


def _tabela_documentos(df: pd.DataFrame):
    with st.expander("Tabela de documentos previstos", expanded=False):
        status_filtro = st.multiselect(
            "Filtrar por status",
            STATUS_ORDEM,
            default=STATUS_ORDEM,
            key="filtro_status",
        )
        df_filtrado = df[df["status"].isin(status_filtro)] if status_filtro else df
        st.dataframe(
            df_filtrado[["codigo", "tipo", "nome_trecho", "status", "titulo"]]
            .rename(columns={
                "codigo": "Código",
                "tipo": "Tipo",
                "nome_trecho": "Trecho",
                "status": "Status",
                "titulo": "Título",
            }),
            use_container_width=True,
            hide_index=True,
        )


# ---------------------------------------------------------------------------
# Página
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Dashboard — SCLME", page_icon="📊", layout="wide")

contrato = _contrato_ativo()

if contrato is None:
    st.title("📊 Dashboard")
    st.warning(
        "Nenhum contrato encontrado. "
        "Acesse **Importação** no menu lateral para criar o contrato e carregar os dados."
    )
    st.stop()

st.title(f"📊 {contrato['nome']}")
if contrato.get("cliente"):
    st.caption(contrato["cliente"])

ultima = _ultima_importacao(contrato["id"])
if ultima:
    st.caption(
        f"Última importação: **{ultima['arquivo_importado']}** "
        f"em {ultima['confirmado_em'][:16].replace('T',' ')} — "
        f"{ultima['total_novos']} novos, {ultima['total_atualizados']} atualizados"
    )

df = carregar_progresso(contrato["id"])

if df.empty:
    st.info(
        "Nenhum documento previsto encontrado. "
        "Importe o **Índice de Documentos (ID)** na página Importação."
    )
    st.stop()

_kpis(df)
st.divider()
_barra_progresso(df)
st.divider()
_grafico_geral(df)
st.divider()
st.subheader("Por Trecho")
_detalhe_por_trecho(df)
st.divider()
_tabela_documentos(df)
