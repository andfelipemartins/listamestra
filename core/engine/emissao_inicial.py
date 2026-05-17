"""
core/engine/emissao_inicial.py

Recalcula os rótulos de EMISSÃO INICIAL para todas as revisões de um documento.

Regra cronológica:
  - Revisão mais antiga (por data_emissao) → "EMISSÃO INICIAL"
  - Seguintes → "REVISÃO 1", "REVISÃO 2", ...
  - A última revisão recebe "REVISÃO FINAL" se SITUAÇÃO indicar aprovação.

Situações que ativam "REVISÃO FINAL":
  APROVADO | PARA APROVAÇÃO | EM COLETA DE ASSINATURAS
"""

import os
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from core.engine.disciplinas import SITUACOES_APROVADO
from core.repositories.revisao_repository import RevisaoRepository
from db.connection import get_connection

_revisao_repository = RevisaoRepository()


def recalcular_emissao_inicial(conn, documento_id: int) -> None:
    """
    Atualiza revisoes.emissao_inicial para todas as revisões do documento.
    Deve ser chamada após qualquer INSERT ou UPDATE em revisoes.
    """
    rows = _revisao_repository.listar_para_recalculo(documento_id, conn=conn)

    n = len(rows)
    for i, row in enumerate(rows):
        if i == 0:
            label = "EMISSÃO INICIAL"
        elif i == n - 1:
            situacao = (row["situacao"] or "").strip().upper()
            if situacao in SITUACOES_APROVADO:
                label = "REVISÃO FINAL"
            else:
                label = f"REVISÃO {i}"
        else:
            label = f"REVISÃO {i}"

        _revisao_repository.atualizar_emissao_inicial(row["id"], label, conn=conn)


def recalcular_por_documento_id(documento_id: int, db_path: Optional[str] = None) -> None:
    """Wrapper para chamadas fora de uma transação aberta."""
    kwargs = {"db_path": db_path} if db_path else {}
    with get_connection(**kwargs) as conn:
        recalcular_emissao_inicial(conn, documento_id)
