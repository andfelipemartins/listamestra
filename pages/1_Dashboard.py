"""
pages/1_Dashboard.py

Dashboard principal do SCLME.
Exibe progresso por status, pizzas por trecho, alertas e barra de progresso geral.
"""

import os
import sys

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core.engine.status import STATUS_ORDEM
from core.exporters.excel_exporter import exportar_lista_mestra, exportar_alertas
from core.services.dashboard_service import DashboardService
from app.session import require_contrato, sidebar_contexto
from core.auth.permissions import widget_seletor_perfil

STATUS_COR: dict[str, str] = {
    "Em Elaboração": "#95a5a6",
    "Em Análise":    "#3498db",
    "Em Revisão":    "#e67e22",
    "Aprovado":      "#27ae60",
}

_service = DashboardService()


# ---------------------------------------------------------------------------
# Componentes de UI
# ---------------------------------------------------------------------------

def _kpis(metricas: dict):
    c0, c1, c2, c3, c4, c5 = st.columns(6)
    c0.metric("Total Previstos", metricas["total_previstos"])
    for col, status in zip([c1, c2, c3, c4], STATUS_ORDEM):
        n = metricas["contagem_por_status"][status]
        pct = metricas["percentual_por_status"][status]
        col.metric(status, n, f"{pct:.1f}%")
    c5.metric(
        "Já Aprovados ✓",
        metricas["ja_aprovados"],
        f"{metricas['percentual_avanco']:.1f}%",
        help="Documentos com ao menos uma revisão aprovada (inclusive com revisões posteriores em curso)",
    )


def _progresso_e_pizza_geral(metricas: dict, distribuicao: dict):
    total = metricas["total_previstos"]
    ja_aprovados = metricas["ja_aprovados"]
    pct = metricas["percentual_avanco"]

    col_bar, col_pizza = st.columns([2, 1])

    with col_bar:
        st.markdown(
            f"#### Progresso geral: **{pct:.1f}%** já aprovado &nbsp;({ja_aprovados} / {total})"
        )
        st.progress(pct / 100)

        fig_bar = px.bar(
            distribuicao["por_trecho"],
            x="nome_trecho",
            y="qtd",
            color="status_atual",
            color_discrete_map=STATUS_COR,
            category_orders={"status_atual": STATUS_ORDEM},
            barmode="stack",
            labels={"nome_trecho": "Trecho", "qtd": "Documentos", "status_atual": "Status Atual"},
        )
        fig_bar.update_layout(
            legend_title_text="Status Atual",
            xaxis_title="",
            margin=dict(t=20, b=0),
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    with col_pizza:
        contagem_geral = distribuicao["geral"]
        contagem_geral = contagem_geral[contagem_geral["qtd"] > 0]
        fig_geral = px.pie(
            contagem_geral,
            names="status_atual",
            values="qtd",
            title="Contrato Geral",
            color="status_atual",
            color_discrete_map=STATUS_COR,
        )
        fig_geral.update_traces(textinfo="percent+label", textposition="inside")
        fig_geral.update_layout(
            showlegend=False,
            margin=dict(t=40, b=0, l=0, r=0),
        )
        st.plotly_chart(fig_geral, use_container_width=True)


def _pizzas_por_trecho(progresso_por_trecho: list[dict]):
    if not progresso_por_trecho:
        return

    st.subheader("Por Trecho")
    cols = st.columns(len(progresso_por_trecho))

    for col, item in zip(cols, progresso_por_trecho):
        nome = item["nome_trecho"]
        contagem = item["contagem_status"]
        contagem = contagem[contagem["qtd"] > 0]

        fig = px.pie(
            contagem,
            names="status_atual",
            values="qtd",
            title=nome.upper(),
            color="status_atual",
            color_discrete_map=STATUS_COR,
        )
        fig.update_traces(textinfo="percent", textposition="inside")
        fig.update_layout(
            showlegend=False,
            margin=dict(t=40, b=0, l=0, r=0),
        )
        col.plotly_chart(fig, use_container_width=True)

        total_t = item["total"]
        aprovados_t = item["ja_aprovados"]
        pct_t = item["percentual"]
        col.progress(pct_t / 100, text=f"{pct_t:.0f}% já aprovado ({aprovados_t}/{total_t})")


def _alertas(alertas: list[dict], dias: int, resumo: dict):
    if not alertas:
        return

    n_analise = resumo["analise_prolongada"]
    n_sem     = resumo["sem_inicio"]
    titulo    = f"{resumo['total']} alerta(s)"
    if n_analise:
        titulo += f" — {n_analise} em análise prolongada (>{dias} dias)"
    if n_sem:
        titulo += f" — {n_sem} sem revisão"

    with st.expander(f"⚠️ {titulo}"):
        if n_analise:
            st.markdown(f"**Em análise ou revisão há mais de {dias} dias**")
            rows = [a for a in alertas if a["tipo"] == "analise_prolongada"]
            df_a = pd.DataFrame(rows)[["codigo", "titulo", "dias", "data_referencia", "mensagem"]]
            df_a.columns = ["Código", "Título", "Dias", "Emitido em", "Situação"]
            st.dataframe(df_a, hide_index=True, use_container_width=True)

        if n_sem:
            st.markdown("**Previstos sem revisão lançada**")
            rows = [a for a in alertas if a["tipo"] == "sem_inicio"]
            df_s = pd.DataFrame(rows)[["codigo", "titulo"]]
            df_s.columns = ["Código", "Título"]
            st.dataframe(df_s, hide_index=True, use_container_width=True)


def _tabela_documentos(df: pd.DataFrame):
    with st.expander("Tabela de documentos previstos"):
        c1, c2 = st.columns([3, 1])
        with c1:
            status_filtro = st.multiselect(
                "Filtrar por status",
                STATUS_ORDEM,
                default=STATUS_ORDEM,
                key="filtro_status",
            )
        with c2:
            tipo_filtro = st.multiselect(
                "Tipo",
                sorted(df["tipo"].dropna().unique()),
                key="filtro_tipo",
            )

        df_filtrado = df.copy()
        if status_filtro:
            df_filtrado = df_filtrado[df_filtrado["status_atual"].isin(status_filtro)]
        if tipo_filtro:
            df_filtrado = df_filtrado[df_filtrado["tipo"].isin(tipo_filtro)]

        st.dataframe(
            df_filtrado[["codigo", "tipo", "nome_trecho", "status_atual", "ja_aprovado", "titulo"]]
            .rename(columns={
                "codigo":      "Código",
                "tipo":        "Tipo",
                "nome_trecho": "Trecho",
                "status_atual":"Status Atual",
                "ja_aprovado": "Já Aprovado",
                "titulo":      "Título",
            }),
            use_container_width=True,
            hide_index=True,
        )


# ---------------------------------------------------------------------------
# Página
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Dashboard — SCLME", page_icon="📊", layout="wide")

widget_seletor_perfil()
contrato = require_contrato()
sidebar_contexto()

st.title(contrato["nome"])

ultima = _service.obter_ultima_importacao(contrato["id"])
if ultima:
    st.caption(
        f"Última importação: **{ultima['arquivo_importado']}** "
        f"em {ultima['confirmado_em'][:16].replace('T', ' ')} — "
        f"{ultima['total_novos']} novos, {ultima['total_atualizados']} atualizados"
    )

df = _service.carregar_progresso(contrato["id"])

if df.empty:
    st.info(
        "Nenhum documento previsto encontrado. "
        "Importe o **Índice de Documentos (ID)** na página Importação."
    )
    st.stop()

# Alertas (threshold configurável na sidebar) + Exportações
with st.sidebar:
    st.markdown("### Alertas")
    dias_alerta = st.number_input(
        "Dias em análise para alertar",
        min_value=1,
        max_value=365,
        value=30,
        step=5,
        key="dias_alerta",
    )

    st.divider()
    st.markdown("### Exportar")

alertas = _service.carregar_alertas(contrato["id"], dias_analise=dias_alerta)
resumo_pendencias = _service.carregar_pendencias_resumidas(
    contrato["id"], dias_analise=dias_alerta, alertas=alertas,
)

with st.sidebar:
    nome_arquivo_lm = contrato["nome"].replace(" ", "_")
    st.download_button(
        "⬇️ Lista Mestra (.xlsx)",
        data=exportar_lista_mestra(df, contrato["nome"]),
        file_name=f"Lista_Mestra_{nome_arquivo_lm}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    if alertas:
        st.download_button(
            "⬇️ Alertas (.xlsx)",
            data=exportar_alertas(alertas, contrato["nome"]),
            file_name=f"Alertas_{nome_arquivo_lm}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

if alertas:
    _alertas(alertas, dias_alerta, resumo_pendencias)
    st.divider()

metricas = _service.carregar_metricas_principais(contrato["id"], df)
distribuicao = _service.carregar_distribuicao_status(contrato["id"], df)
por_trecho = _service.carregar_progresso_por_trecho(contrato["id"], df)

_kpis(metricas)
st.divider()
_progresso_e_pizza_geral(metricas, distribuicao)
st.divider()
_pizzas_por_trecho(por_trecho)
st.divider()
_tabela_documentos(df)
