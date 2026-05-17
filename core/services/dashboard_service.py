"""
core/services/dashboard_service.py

Regras de aplicacao do Dashboard.

Concentra consulta, agregacao e preparacao dos dados exibidos na pagina.
Nao depende de Streamlit nem de Plotly: retorna DataFrames e dicts prontos
para a pagina renderizar.
"""

from typing import Optional

import pandas as pd

from core.engine.status import (
    NOME_TRECHO,
    STATUS_ORDEM,
    carregar_alertas,
    carregar_progresso,
)
from core.formatacao import disciplina_do_codigo
from core.repositories.importacao_repository import ImportacaoRepository
from core.services.importacao_service import ImportacaoService


class DashboardService:
    def __init__(
        self,
        db_path: Optional[str] = None,
        importacao_service: Optional[ImportacaoService] = None,
    ):
        self._db_path = db_path
        self._importacao_service = importacao_service or ImportacaoService(
            ImportacaoRepository(db_path)
        )

    # ------------------------------------------------------------------
    # Fontes de dados
    # ------------------------------------------------------------------

    def carregar_progresso(self, contrato_id: int) -> pd.DataFrame:
        """DataFrame de previstos com status_atual, ja_aprovado e nome_trecho."""
        return carregar_progresso(contrato_id, self._db_path)

    def carregar_alertas(
        self, contrato_id: int, dias_analise: int = 30
    ) -> list[dict]:
        return carregar_alertas(contrato_id, dias_analise, self._db_path)

    def _df(
        self, contrato_id: int, df: Optional[pd.DataFrame]
    ) -> pd.DataFrame:
        return df if df is not None else self.carregar_progresso(contrato_id)

    # ------------------------------------------------------------------
    # Métricas
    # ------------------------------------------------------------------

    @staticmethod
    def _metricas_zeradas() -> dict:
        zeros_int = {s: 0 for s in STATUS_ORDEM}
        zeros_pct = {s: 0.0 for s in STATUS_ORDEM}
        return {
            "total_previstos": 0,
            "ja_aprovados": 0,
            "percentual_avanco": 0.0,
            "contagem_por_status": zeros_int,
            "percentual_por_status": zeros_pct,
            "total_em_elaboracao": 0,
            "total_em_analise": 0,
            "total_em_revisao": 0,
            "total_aprovados": 0,
        }

    def _calcular_metricas(self, df: pd.DataFrame) -> dict:
        total = len(df)
        if total == 0:
            return self._metricas_zeradas()
        counts = df["status_atual"].value_counts()
        ja_aprovados = int(df["ja_aprovado"].sum())
        contagem = {s: int(counts.get(s, 0)) for s in STATUS_ORDEM}
        return {
            "total_previstos": total,
            "ja_aprovados": ja_aprovados,
            "percentual_avanco": ja_aprovados / total * 100,
            "contagem_por_status": contagem,
            "percentual_por_status": {s: v / total * 100 for s, v in contagem.items()},
            "total_em_elaboracao": contagem["Em Elaboração"],
            "total_em_analise": contagem["Em Análise"],
            "total_em_revisao": contagem["Em Revisão"],
            "total_aprovados": contagem["Aprovado"],
        }

    def carregar_metricas_principais(
        self, contrato_id: int, df: Optional[pd.DataFrame] = None
    ) -> dict:
        return self._calcular_metricas(self._df(contrato_id, df))

    # ------------------------------------------------------------------
    # Distribuição por status
    # ------------------------------------------------------------------

    def carregar_distribuicao_status(
        self, contrato_id: int, df: Optional[pd.DataFrame] = None
    ) -> dict:
        """Retorna dois DataFrames: 'geral' (status, qtd) e 'por_trecho' (trecho, status, qtd).

        por_trecho ja vem reindexado para garantir todas as combinacoes
        trecho × status (preserva semantica do grafico empilhado).
        """
        df = self._df(contrato_id, df)
        if df.empty:
            return {
                "geral": pd.DataFrame(columns=["status_atual", "qtd"]),
                "por_trecho": pd.DataFrame(
                    columns=["nome_trecho", "status_atual", "qtd"]
                ),
            }

        geral = (
            df["status_atual"]
            .value_counts()
            .reindex(STATUS_ORDEM, fill_value=0)
            .reset_index()
        )
        geral.columns = ["status_atual", "qtd"]

        contagem = (
            df.groupby(["nome_trecho", "status_atual"])
            .size()
            .reset_index(name="qtd")
        )
        trechos = contagem["nome_trecho"].unique().tolist()
        completo = pd.MultiIndex.from_product(
            [trechos, STATUS_ORDEM], names=["nome_trecho", "status_atual"]
        )
        contagem = (
            contagem.set_index(["nome_trecho", "status_atual"])
            .reindex(completo, fill_value=0)
            .reset_index()
        )
        return {"geral": geral, "por_trecho": contagem}

    # ------------------------------------------------------------------
    # Progresso por trecho
    # ------------------------------------------------------------------

    def carregar_progresso_por_trecho(
        self, contrato_id: int, df: Optional[pd.DataFrame] = None
    ) -> list[dict]:
        """Lista de dicts por trecho com total, ja_aprovados, percentual e contagem por status."""
        df = self._df(contrato_id, df)
        if df.empty:
            return []
        trechos = sorted(df["trecho"].unique())
        resultado: list[dict] = []
        for trecho in trechos:
            df_t = df[df["trecho"] == trecho]
            total = len(df_t)
            ja_ap = int(df_t["ja_aprovado"].sum())
            contagem = (
                df_t["status_atual"]
                .value_counts()
                .reindex(STATUS_ORDEM, fill_value=0)
                .reset_index()
            )
            contagem.columns = ["status_atual", "qtd"]
            resultado.append({
                "trecho": trecho,
                "nome_trecho": NOME_TRECHO.get(trecho, trecho),
                "total": total,
                "ja_aprovados": ja_ap,
                "percentual": ja_ap / total * 100 if total else 0.0,
                "contagem_status": contagem,
            })
        return resultado

    # ------------------------------------------------------------------
    # Progresso por disciplina
    # ------------------------------------------------------------------

    def carregar_progresso_por_disciplina(
        self, contrato_id: int, df: Optional[pd.DataFrame] = None
    ) -> list[dict]:
        """Lista de dicts por disciplina (classe+subclasse derivada do codigo)."""
        df = self._df(contrato_id, df)
        if df.empty:
            return []
        df = df.copy()
        df["disciplina"] = df["codigo"].apply(disciplina_do_codigo).fillna("")
        disciplinas = sorted(d for d in df["disciplina"].unique() if d)
        resultado: list[dict] = []
        for disc in disciplinas:
            df_d = df[df["disciplina"] == disc]
            total = len(df_d)
            ja_ap = int(df_d["ja_aprovado"].sum())
            resultado.append({
                "disciplina": disc,
                "total": total,
                "ja_aprovados": ja_ap,
                "percentual": ja_ap / total * 100 if total else 0.0,
            })
        return resultado

    # ------------------------------------------------------------------
    # Pendências / alertas resumidos
    # ------------------------------------------------------------------

    def carregar_pendencias_resumidas(
        self,
        contrato_id: int,
        dias_analise: int = 30,
        alertas: Optional[list[dict]] = None,
    ) -> dict:
        if alertas is None:
            alertas = self.carregar_alertas(contrato_id, dias_analise)
        return {
            "total": len(alertas),
            "analise_prolongada": sum(
                1 for a in alertas if a.get("tipo") == "analise_prolongada"
            ),
            "sem_inicio": sum(1 for a in alertas if a.get("tipo") == "sem_inicio"),
            "alertas": alertas,
        }

    # ------------------------------------------------------------------
    # Importações
    # ------------------------------------------------------------------

    def obter_ultima_importacao(self, contrato_id: int) -> Optional[dict]:
        return self._importacao_service.obter_ultima_importacao(contrato_id)

    def carregar_ultimas_importacoes(
        self, contrato_id: int, limite: int = 10
    ) -> list[dict]:
        return self._importacao_service.listar_historico_importacoes(
            contrato_id, limite
        )

    # ------------------------------------------------------------------
    # Resumo consolidado
    # ------------------------------------------------------------------

    def carregar_resumo_dashboard(
        self, contrato_id: int, dias_analise: int = 30
    ) -> dict:
        """Bundle com todos os dados do dashboard em uma so passagem.

        Carrega o DataFrame de progresso uma vez e reaproveita para metricas,
        distribuicao, agregacoes por trecho e disciplina.
        """
        df = self.carregar_progresso(contrato_id)
        alertas = self.carregar_alertas(contrato_id, dias_analise)
        return {
            "progresso_df": df,
            "metricas_principais": self._calcular_metricas(df),
            "distribuicao_status": self.carregar_distribuicao_status(contrato_id, df),
            "progresso_por_trecho": self.carregar_progresso_por_trecho(contrato_id, df),
            "progresso_por_disciplina": self.carregar_progresso_por_disciplina(
                contrato_id, df
            ),
            "alertas": alertas,
            "resumo_pendencias": self.carregar_pendencias_resumidas(
                contrato_id, dias_analise, alertas
            ),
            "ultima_importacao": self.obter_ultima_importacao(contrato_id),
            "ultimas_importacoes": self.carregar_ultimas_importacoes(contrato_id),
        }
