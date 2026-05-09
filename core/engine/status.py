"""
core/engine/status.py

Classificação de status documental — regra de negócio central do SCLME.

Um documento previsto (documentos_previstos) tem seu status determinado
cruzando-o com a última revisão importada da Lista de Documentos.

Esta é a fundação do Motor de Status completo (Marco 9).
"""

import os
import sys
from typing import Optional

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db.connection import get_connection

# ---------------------------------------------------------------------------
# Constantes de domínio
# ---------------------------------------------------------------------------

STATUS_ORDEM = ["Em Elaboração", "Em Análise", "Em Revisão", "Aprovado"]

NOME_TRECHO = {
    "00": "Geral",
    "19": "Oratório",
    "23": "São Mateus",
    "25": "Ragueb Chohfi",
}

# ---------------------------------------------------------------------------
# Lógica de status
# ---------------------------------------------------------------------------

def classificar_status(
    situacao: Optional[str],
    data_emissao: Optional[str],
) -> str:
    """
    Classifica o status de um documento a partir dos campos da última revisão.

    Regras (em ordem de precedência):
    1. situacao contém "APROVADO" (sem "NÃO") → Aprovado
    2. situacao contém "NÃO APROVADO"          → Em Revisão
    3. data_emissao preenchida                 → Em Análise
    4. Caso contrário                          → Em Elaboração

    Documentos ausentes na Lista (situacao=None, data_emissao=None) são
    corretamente classificados como "Em Elaboração".
    """
    # pandas representa NULL como float NaN; normaliza para string vazia
    s = "" if (not situacao or isinstance(situacao, float)) else str(situacao).upper()
    de = None if (not data_emissao or isinstance(data_emissao, float)) else data_emissao

    if "APROVADO" in s and "NÃO" not in s:
        return "Aprovado"
    if "NÃO APROVADO" in s:
        return "Em Revisão"
    if de:
        return "Em Análise"
    return "Em Elaboração"


def carregar_progresso(
    contrato_id: int,
    db_path: Optional[str] = None,
) -> pd.DataFrame:
    """
    Retorna um DataFrame com status calculado para cada documento previsto.

    Colunas: codigo, titulo, trecho, nome_trecho, tipo, situacao,
             data_emissao, status

    Documentos previstos sem correspondente na Lista ficam com
    situacao=None e data_emissao=None → status "Em Elaboração".
    """
    kwargs = {"db_path": db_path} if db_path else {}
    with get_connection(**kwargs) as conn:
        rows = conn.execute(
            """
            SELECT
                dp.codigo,
                dp.titulo,
                COALESCE(dp.trecho, '00') AS trecho,
                dp.tipo,
                r.situacao,
                r.data_emissao
            FROM documentos_previstos dp
            LEFT JOIN documentos d
                   ON d.contrato_id = dp.contrato_id AND d.codigo = dp.codigo
            LEFT JOIN revisoes r
                   ON r.documento_id = d.id AND r.ultima_revisao = 1
            WHERE dp.contrato_id = ? AND dp.ativo = 1
            ORDER BY dp.trecho, dp.codigo
            """,
            (contrato_id,),
        ).fetchall()

    df = pd.DataFrame([dict(r) for r in rows])
    if df.empty:
        return df

    df["status"] = df.apply(
        lambda row: classificar_status(row["situacao"], row["data_emissao"]),
        axis=1,
    )
    df["nome_trecho"] = df["trecho"].map(NOME_TRECHO).fillna(df["trecho"])
    return df
