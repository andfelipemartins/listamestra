"""
core/engine/status.py

Classificação de status documental — regra de negócio central do SCLME.

Um documento previsto (documentos_previstos) tem seu status determinado
cruzando-o com a última revisão importada da Lista de Documentos.

Esta é a fundação do Motor de Status completo (Marco 9).
"""

import os
import sys
from datetime import date
from typing import Optional

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from core.repositories.documento_repository import DocumentoRepository
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


def carregar_alertas(
    contrato_id: int,
    dias_analise: int = 30,
    db_path: Optional[str] = None,
) -> list[dict]:
    """
    Retorna alertas documentais que requerem atenção.

    Tipos:
    - 'analise_prolongada': última revisão emitida mas não aprovada há > dias_analise dias
    - 'sem_inicio': previsto no ID mas sem nenhuma revisão lançada

    Cada item: tipo, codigo, titulo, dias, data_referencia, mensagem
    """
    kwargs = {"db_path": db_path} if db_path else {}
    alertas: list[dict] = []

    with get_connection(**kwargs) as conn:
        # Previstos com última revisão emitida — filtra os não-aprovados em Python
        rows = conn.execute(
            """
            SELECT dp.codigo,
                   COALESCE(d.titulo, dp.titulo) AS titulo,
                   r.situacao,
                   r.data_emissao,
                   CAST(julianday('now') - julianday(r.data_emissao) AS INTEGER) AS dias
            FROM documentos_previstos dp
            JOIN documentos d ON d.contrato_id = dp.contrato_id AND d.codigo = dp.codigo
            JOIN revisoes r ON r.documento_id = d.id AND r.ultima_revisao = 1
            WHERE dp.contrato_id = ? AND dp.ativo = 1
              AND r.data_emissao IS NOT NULL
            """,
            (contrato_id,),
        ).fetchall()

        for row in rows:
            status = classificar_status(row["situacao"], row["data_emissao"])
            if status in ("Em Análise", "Em Revisão") and row["dias"] > dias_analise:
                alertas.append({
                    "tipo": "analise_prolongada",
                    "codigo": row["codigo"],
                    "titulo": row["titulo"] or "—",
                    "dias": row["dias"],
                    "data_referencia": row["data_emissao"],
                    "mensagem": f"{status} há {row['dias']} dias",
                })

        # Previstos sem nenhuma revisão
        rows_sem = DocumentoRepository(db_path).listar_documentos_sem_revisao(
            contrato_id, conn=conn
        )

        for row in rows_sem:
            alertas.append({
                "tipo": "sem_inicio",
                "codigo": row["codigo"],
                "titulo": row["titulo"] or "—",
                "dias": None,
                "data_referencia": None,
                "mensagem": "Previsto no ID mas sem revisão lançada",
            })

    return alertas


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
                r.data_emissao,
                CASE WHEN EXISTS (
                    SELECT 1 FROM revisoes rh
                    WHERE rh.documento_id = d.id
                      AND (
                          rh.label_revisao = '0'
                          OR rh.label_revisao GLOB '[A-Z]'
                      )
                ) THEN 1 ELSE 0 END AS ja_aprovado
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

    df["status_atual"] = df.apply(
        lambda row: classificar_status(row["situacao"], row["data_emissao"]),
        axis=1,
    )
    # ja_aprovado: marco histórico do documento na Lista Mestra.
    # Regra: label_revisao = '0' (emissão inicial aprovada) OU letra maiúscula pura (A, B, C…).
    # Letras compostas (A1, B1…) e numéricas positivas (1, 2…) NÃO contam como aprovação.
    # Independe de situacao, versao ou status atual. Contado por documento (não por revisão).
    df["nome_trecho"] = df["trecho"].map(NOME_TRECHO).fillna(df["trecho"])
    return df
