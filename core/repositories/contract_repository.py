"""
core/repositories/contract_repository.py

Acesso a dados de contratos.

Esta camada concentra SQL de contratos para manter paginas Streamlit livres de
consultas diretas e preparar uma futura troca de banco/interface.
"""

from typing import Optional

from db.connection import get_connection


class ContractRepository:
    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path

    def _connection_kwargs(self) -> dict:
        return {"db_path": self._db_path} if self._db_path else {}

    def verificar_banco(self) -> bool:
        try:
            with get_connection(**self._connection_kwargs()) as conn:
                conn.execute("SELECT 1 FROM contratos LIMIT 1")
            return True
        except Exception:
            return False

    def listar_contratos_ativos(self) -> list[dict]:
        with get_connection(**self._connection_kwargs()) as conn:
            rows = conn.execute(
                """
                SELECT id, nome, cliente
                FROM contratos
                WHERE ativo = 1
                ORDER BY nome
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def obter_primeiro_contrato_ativo(self) -> dict | None:
        with get_connection(**self._connection_kwargs()) as conn:
            row = conn.execute(
                """
                SELECT id, nome, cliente
                FROM contratos
                WHERE ativo = 1
                ORDER BY id
                LIMIT 1
                """
            ).fetchone()
        return dict(row) if row else None

    def obter_contrato_por_id(self, contrato_id: int) -> dict | None:
        with get_connection(**self._connection_kwargs()) as conn:
            row = conn.execute(
                """
                SELECT id, nome, cliente
                FROM contratos
                WHERE id = ?
                """,
                (contrato_id,),
            ).fetchone()
        return dict(row) if row else None

    def criar_contrato(self, nome: str, cliente: str = "") -> int:
        with get_connection(**self._connection_kwargs()) as conn:
            cur = conn.execute(
                "INSERT INTO contratos (nome, cliente) VALUES (?, ?)",
                (nome, cliente),
            )
            return cur.lastrowid

    def contar_documentos_previstos(self, contrato_id: int) -> int:
        with get_connection(**self._connection_kwargs()) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM documentos_previstos
                WHERE contrato_id = ?
                """,
                (contrato_id,),
            ).fetchone()
        return int(row["total"])

    def contar_documentos_movimentados(self, contrato_id: int) -> int:
        with get_connection(**self._connection_kwargs()) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM documentos
                WHERE contrato_id = ?
                """,
                (contrato_id,),
            ).fetchone()
        return int(row["total"])

    def contar_revisoes(self, contrato_id: int) -> int:
        with get_connection(**self._connection_kwargs()) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM revisoes r
                JOIN documentos d ON d.id = r.documento_id
                WHERE d.contrato_id = ?
                """,
                (contrato_id,),
            ).fetchone()
        return int(row["total"])

    def obter_metricas_contrato(self, contrato_id: int) -> dict:
        return {
            "previstos": self.contar_documentos_previstos(contrato_id),
            "documentos": self.contar_documentos_movimentados(contrato_id),
            "revisoes": self.contar_revisoes(contrato_id),
        }

