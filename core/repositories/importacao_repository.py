"""
core/repositories/importacao_repository.py

Acesso a dados de importacoes.

Esta camada concentra SQL da tabela importacoes para manter paginas Streamlit
livres de consultas diretas e preparar uma futura troca de banco/interface.
"""

from contextlib import contextmanager
from typing import Optional

from db.connection import get_connection


class ImportacaoRepository:
    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path

    def _connection_kwargs(self) -> dict:
        return {"db_path": self._db_path} if self._db_path else {}

    @contextmanager
    def _connect(self, conn=None):
        if conn is not None:
            yield conn
            return
        with get_connection(**self._connection_kwargs()) as owned_conn:
            yield owned_conn

    def listar_importacoes(
        self,
        contrato_id: int | None = None,
        status: str | None = None,
        limite: int | None = None,
    ) -> list[dict]:
        where = []
        params = []

        if contrato_id is not None:
            where.append("contrato_id = ?")
            params.append(contrato_id)
        if status is not None:
            where.append("status = ?")
            params.append(status)

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        limite_sql = ""
        if limite is not None:
            limite_sql = "LIMIT ?"
            params.append(limite)

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, contrato_id, origem, arquivo_importado, total_registros,
                       total_erros, total_novos, total_atualizados, status,
                       usuario, criado_em, confirmado_em
                FROM importacoes
                {where_sql}
                ORDER BY id DESC
                {limite_sql}
                """,
                tuple(params),
            ).fetchall()
        return [dict(r) for r in rows]

    def listar_historico_importacoes(self, contrato_id: int, limite: int = 10) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT origem, arquivo_importado, total_registros, total_novos,
                       total_atualizados, total_erros, status, confirmado_em
                FROM importacoes
                WHERE contrato_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (contrato_id, limite),
            ).fetchall()
        return [dict(r) for r in rows]

    def obter_ultima_importacao(
        self,
        contrato_id: int,
        status: str | None = "concluido",
    ) -> dict | None:
        status_sql = "AND status = ?" if status is not None else ""
        params = (contrato_id, status) if status is not None else (contrato_id,)

        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT origem, arquivo_importado, total_registros, total_novos,
                       total_atualizados, total_erros, confirmado_em
                FROM importacoes
                WHERE contrato_id = ?
                  {status_sql}
                ORDER BY id DESC
                LIMIT 1
                """,
                params,
            ).fetchone()
        return dict(row) if row else None

    def contar_importacoes(self, contrato_id: int | None = None) -> int:
        if contrato_id is None:
            sql = "SELECT COUNT(*) AS total FROM importacoes"
            params = ()
        else:
            sql = "SELECT COUNT(*) AS total FROM importacoes WHERE contrato_id = ?"
            params = (contrato_id,)

        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return int(row["total"])

    def buscar_importacao_por_id(self, importacao_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, contrato_id, origem, arquivo_importado, total_registros,
                       total_erros, total_novos, total_atualizados, status,
                       usuario, criado_em, confirmado_em
                FROM importacoes
                WHERE id = ?
                """,
                (importacao_id,),
            ).fetchone()
        return dict(row) if row else None

    def registrar_importacao(
        self,
        contrato_id: int,
        origem: str,
        arquivo_importado: str,
        total_registros: int = 0,
        status: str = "em_andamento",
        usuario: str | None = None,
        conn=None,
    ) -> int:
        with self._connect(conn) as active_conn:
            cur = active_conn.execute(
                """
                INSERT INTO importacoes
                    (contrato_id, origem, arquivo_importado, total_registros, status, usuario)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    contrato_id,
                    origem,
                    arquivo_importado,
                    total_registros,
                    status,
                    usuario,
                ),
            )
            return cur.lastrowid

    def finalizar_importacao(
        self,
        importacao_id: int,
        total_erros: int,
        total_novos: int,
        total_atualizados: int,
        status: str = "concluido",
        conn=None,
    ) -> None:
        with self._connect(conn) as active_conn:
            active_conn.execute(
                """
                UPDATE importacoes SET
                    total_erros       = ?,
                    total_novos       = ?,
                    total_atualizados = ?,
                    status            = ?,
                    confirmado_em     = datetime('now')
                WHERE id = ?
                """,
                (
                    total_erros,
                    total_novos,
                    total_atualizados,
                    status,
                    importacao_id,
                ),
            )
