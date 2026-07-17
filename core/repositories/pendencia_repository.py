"""
core/repositories/pendencia_repository.py

Persistencia das decisoes humanas sobre pendencias calculadas.
"""

from contextlib import contextmanager
from typing import Optional

from db.connection import get_connection


ACOES_DISPENSA = ("resolvida", "ignorada")


def _tipo_valor(tipo) -> str:
    return str(getattr(tipo, "value", tipo))


class PendenciaRepository:
    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path

    def _connection_kwargs(self) -> dict:
        return {"db_path": self._db_path} if self._db_path else {}

    @contextmanager
    def _connect(self, conn=None):
        if conn is not None:
            yield conn
            return
        with get_connection(**self._connection_kwargs()) as owned:
            yield owned

    def listar_por_contrato(self, contrato_id: int, conn=None) -> list[dict]:
        with self._connect(conn) as c:
            rows = c.execute(
                """
                SELECT id, contrato_id, tipo_pendencia, chave, acao,
                       observacao, perfil, criado_em
                FROM pendencias_dispensas
                WHERE contrato_id = ?
                ORDER BY tipo_pendencia, chave
                """,
                (contrato_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def buscar_por_chave(
        self,
        contrato_id: int,
        tipo_pendencia,
        chave: str,
        conn=None,
    ) -> dict | None:
        with self._connect(conn) as c:
            row = c.execute(
                """
                SELECT id, contrato_id, tipo_pendencia, chave, acao,
                       observacao, perfil, criado_em
                FROM pendencias_dispensas
                WHERE contrato_id = ? AND tipo_pendencia = ? AND chave = ?
                """,
                (contrato_id, _tipo_valor(tipo_pendencia), str(chave)),
            ).fetchone()
        return dict(row) if row else None

    def dispensar(
        self,
        contrato_id: int,
        tipo_pendencia,
        chave: str,
        acao: str,
        observacao: Optional[str] = None,
        perfil: Optional[str] = None,
        conn=None,
    ) -> int:
        if acao not in ACOES_DISPENSA:
            raise ValueError("Acao deve ser 'resolvida' ou 'ignorada'.")

        tipo = _tipo_valor(tipo_pendencia)
        with self._connect(conn) as c:
            c.execute(
                """
                INSERT OR IGNORE INTO pendencias_dispensas
                    (contrato_id, tipo_pendencia, chave, acao, observacao, perfil)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (contrato_id, tipo, str(chave), acao, observacao, perfil),
            )
            row = c.execute(
                """
                SELECT id FROM pendencias_dispensas
                WHERE contrato_id = ? AND tipo_pendencia = ? AND chave = ?
                """,
                (contrato_id, tipo, str(chave)),
            ).fetchone()
        return int(row["id"])

    def reativar(self, contrato_id: int, dispensa_id: int, conn=None) -> bool:
        with self._connect(conn) as c:
            cur = c.execute(
                """
                DELETE FROM pendencias_dispensas
                WHERE id = ? AND contrato_id = ?
                """,
                (dispensa_id, contrato_id),
            )
        return bool(cur.rowcount)

    def contar_por_contrato(self, contrato_id: int, conn=None) -> int:
        with self._connect(conn) as c:
            row = c.execute(
                "SELECT COUNT(*) AS total FROM pendencias_dispensas WHERE contrato_id = ?",
                (contrato_id,),
            ).fetchone()
        return int(row["total"])
