"""
core/engine/comparacao.py

Comparação entre o Índice de Documentos (documentos_previstos) e
a Lista de Documentos (documentos), base do Marco 6.
"""

import os
import sys
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db.connection import get_connection
from core.engine.status import NOME_TRECHO


@dataclass
class ResultadoComparacao:
    """
    Resultado da comparação ID × Lista para um contrato.

    ausentes    — previstos no ID sem entrada na Lista
    extras      — na Lista sem correspondência no ID
    divergencias — código presente nos dois lados, mas título diferente
    encontrados — previstos que têm correspondência na Lista (com ou sem divergência)
    """
    ausentes:     pd.DataFrame = field(default_factory=pd.DataFrame)
    extras:       pd.DataFrame = field(default_factory=pd.DataFrame)
    divergencias: pd.DataFrame = field(default_factory=pd.DataFrame)
    encontrados:  pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def total_previstos(self) -> int:
        return len(self.ausentes) + len(self.encontrados)

    @property
    def total_ausentes(self) -> int:
        return len(self.ausentes)

    @property
    def total_extras(self) -> int:
        return len(self.extras)

    @property
    def total_divergencias(self) -> int:
        return len(self.divergencias)

    @property
    def total_encontrados(self) -> int:
        return len(self.encontrados)


def _add_nome_trecho(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "trecho" not in df.columns:
        return df
    df = df.copy()
    df["nome_trecho"] = df["trecho"].map(NOME_TRECHO).fillna(df["trecho"])
    return df


def comparar_id_lista(
    contrato_id: int,
    db_path: Optional[str] = None,
) -> ResultadoComparacao:
    """
    Compara documentos_previstos (ID) com documentos (Lista) para o contrato.

    Retorna um ResultadoComparacao com os quatro DataFrames populados.
    Cada DataFrame inclui a coluna nome_trecho para exibição.
    """
    kwargs = {"db_path": db_path} if db_path else {}
    with get_connection(**kwargs) as conn:

        ausentes_rows = conn.execute(
            """
            SELECT dp.codigo, dp.titulo, COALESCE(dp.trecho, '00') AS trecho, dp.tipo
            FROM documentos_previstos dp
            LEFT JOIN documentos d
                   ON d.contrato_id = dp.contrato_id AND d.codigo = dp.codigo
            WHERE dp.contrato_id = ? AND dp.ativo = 1 AND d.id IS NULL
            ORDER BY dp.trecho, dp.codigo
            """,
            (contrato_id,),
        ).fetchall()

        extras_rows = conn.execute(
            """
            SELECT d.codigo, d.titulo, COALESCE(d.trecho, '00') AS trecho, d.tipo
            FROM documentos d
            LEFT JOIN documentos_previstos dp
                   ON dp.contrato_id = d.contrato_id
                  AND dp.codigo = d.codigo
                  AND dp.ativo = 1
            WHERE d.contrato_id = ? AND dp.id IS NULL
            ORDER BY d.trecho, d.codigo
            """,
            (contrato_id,),
        ).fetchall()

        divergencias_rows = conn.execute(
            """
            SELECT
                dp.codigo,
                COALESCE(dp.trecho, '00') AS trecho,
                dp.tipo,
                dp.titulo      AS titulo_id,
                d.titulo       AS titulo_lista
            FROM documentos_previstos dp
            JOIN documentos d
              ON d.contrato_id = dp.contrato_id AND d.codigo = dp.codigo
            WHERE dp.contrato_id = ? AND dp.ativo = 1
              AND dp.titulo IS NOT NULL AND dp.titulo != ''
              AND d.titulo  IS NOT NULL AND d.titulo  != ''
              AND TRIM(dp.titulo) != TRIM(d.titulo)
            ORDER BY dp.trecho, dp.codigo
            """,
            (contrato_id,),
        ).fetchall()

        encontrados_rows = conn.execute(
            """
            SELECT dp.codigo, dp.titulo, COALESCE(dp.trecho, '00') AS trecho, dp.tipo
            FROM documentos_previstos dp
            JOIN documentos d
              ON d.contrato_id = dp.contrato_id AND d.codigo = dp.codigo
            WHERE dp.contrato_id = ? AND dp.ativo = 1
            ORDER BY dp.trecho, dp.codigo
            """,
            (contrato_id,),
        ).fetchall()

    def _to_df(rows):
        return pd.DataFrame([dict(r) for r in rows])

    return ResultadoComparacao(
        ausentes=_add_nome_trecho(_to_df(ausentes_rows)),
        extras=_add_nome_trecho(_to_df(extras_rows)),
        divergencias=_add_nome_trecho(_to_df(divergencias_rows)),
        encontrados=_add_nome_trecho(_to_df(encontrados_rows)),
    )
