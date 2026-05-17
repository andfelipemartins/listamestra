"""
core/repositories/revisao_repository.py

Acesso a dados de revisoes.

Concentra SQL da tabela revisoes para manter paginas Streamlit, engines e
importers livres de consultas diretas. Aceita uma conexao externa (`conn`)
para participar de transacoes ja abertas (importers, cadastro manual).
"""

from contextlib import contextmanager
from typing import Iterable, Optional

from db.connection import get_connection


_CAMPOS_ATUALIZAVEIS = (
    "revisao",
    "versao",
    "label_revisao",
    "emissao_inicial",
    "data_elaboracao",
    "data_emissao",
    "data_analise",
    "dias_elaboracao",
    "dias_analise",
    "situacao_real",
    "situacao",
    "retorno",
    "emissao_circular",
    "analise_circular",
    "data_circular",
    "ultima_revisao",
    "origem",
)


class RevisaoRepository:
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

    # ------------------------------------------------------------------
    # Leitura
    # ------------------------------------------------------------------

    def buscar_por_id(self, revisao_id: int, conn=None) -> dict | None:
        with self._connect(conn) as c:
            row = c.execute(
                "SELECT * FROM revisoes WHERE id = ?",
                (revisao_id,),
            ).fetchone()
        return dict(row) if row else None

    def buscar_por_label_versao(
        self,
        documento_id: int,
        label_revisao: str,
        versao: int,
        conn=None,
    ) -> dict | None:
        with self._connect(conn) as c:
            row = c.execute(
                """
                SELECT * FROM revisoes
                WHERE documento_id = ? AND label_revisao = ? AND versao = ?
                """,
                (documento_id, label_revisao, versao),
            ).fetchone()
        return dict(row) if row else None

    def existe_revisao(
        self,
        documento_id: int,
        label_revisao: str,
        versao: int,
        conn=None,
    ) -> bool:
        with self._connect(conn) as c:
            row = c.execute(
                """
                SELECT 1 FROM revisoes
                WHERE documento_id = ? AND label_revisao = ? AND versao = ?
                LIMIT 1
                """,
                (documento_id, label_revisao, versao),
            ).fetchone()
        return row is not None

    def listar_por_documento(
        self, documento_id: int, conn=None
    ) -> list[dict]:
        """Historico completo ordenado cronologicamente (mesma ordem da pagina Documento)."""
        with self._connect(conn) as c:
            rows = c.execute(
                """
                SELECT r.id, r.revisao, r.versao, r.label_revisao, r.emissao_inicial,
                       r.data_elaboracao, r.data_emissao, r.data_analise,
                       r.dias_elaboracao, r.dias_analise,
                       r.situacao_real, r.situacao, r.retorno,
                       r.emissao_circular, r.analise_circular, r.data_circular,
                       r.ultima_revisao, r.origem, r.criado_em
                FROM revisoes r
                WHERE r.documento_id = ?
                ORDER BY
                    CASE WHEN r.data_emissao IS NULL THEN 1 ELSE 0 END,
                    r.data_emissao ASC,
                    r.revisao ASC,
                    r.versao ASC
                """,
                (documento_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def listar_resumo_por_documento(
        self, documento_id: int, conn=None
    ) -> list[dict]:
        """Versao reduzida (Cadastro Manual)."""
        with self._connect(conn) as c:
            rows = c.execute(
                """
                SELECT label_revisao, versao, emissao_inicial, data_emissao, situacao
                FROM revisoes
                WHERE documento_id = ?
                ORDER BY
                    CASE WHEN data_emissao IS NULL THEN 1 ELSE 0 END,
                    data_emissao ASC, revisao ASC, versao ASC
                """,
                (documento_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def buscar_ultima_revisao(
        self, documento_id: int, conn=None
    ) -> dict | None:
        with self._connect(conn) as c:
            row = c.execute(
                """
                SELECT id, revisao, versao, label_revisao, emissao_inicial,
                       data_emissao, situacao, ultima_revisao
                FROM revisoes
                WHERE documento_id = ?
                ORDER BY
                    CASE WHEN data_emissao IS NULL THEN 1 ELSE 0 END ASC,
                    data_emissao DESC,
                    revisao DESC,
                    versao DESC,
                    id DESC
                LIMIT 1
                """,
                (documento_id,),
            ).fetchone()
        return dict(row) if row else None

    def listar_por_contrato(
        self, contrato_id: int, conn=None
    ) -> list[dict]:
        with self._connect(conn) as c:
            rows = c.execute(
                """
                SELECT r.id, r.documento_id, d.codigo, r.revisao, r.versao,
                       r.label_revisao, r.emissao_inicial, r.data_emissao,
                       r.situacao, r.ultima_revisao
                FROM revisoes r
                JOIN documentos d ON d.id = r.documento_id
                WHERE d.contrato_id = ?
                ORDER BY d.codigo, r.data_emissao
                """,
                (contrato_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def listar_para_recalculo(
        self, documento_id: int, conn=None
    ) -> list[dict]:
        """Linha minima usada por engine.emissao_inicial (id, data_emissao, situacao)."""
        with self._connect(conn) as c:
            rows = c.execute(
                """
                SELECT id, data_emissao, situacao
                FROM revisoes
                WHERE documento_id = ?
                ORDER BY
                    CASE WHEN data_emissao IS NULL THEN 1 ELSE 0 END,
                    data_emissao ASC,
                    revisao ASC,
                    versao ASC
                """,
                (documento_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Contagem
    # ------------------------------------------------------------------

    def contar_por_contrato(self, contrato_id: int, conn=None) -> int:
        with self._connect(conn) as c:
            row = c.execute(
                """
                SELECT COUNT(*) AS total
                FROM revisoes r
                JOIN documentos d ON d.id = r.documento_id
                WHERE d.contrato_id = ?
                """,
                (contrato_id,),
            ).fetchone()
        return int(row["total"])

    def contar_por_documento(self, documento_id: int, conn=None) -> int:
        with self._connect(conn) as c:
            row = c.execute(
                "SELECT COUNT(*) AS total FROM revisoes WHERE documento_id = ?",
                (documento_id,),
            ).fetchone()
        return int(row["total"])

    # ------------------------------------------------------------------
    # Escrita
    # ------------------------------------------------------------------

    def criar_revisao(self, data: dict, conn=None) -> int:
        if "documento_id" not in data:
            raise ValueError("documento_id e obrigatorio.")

        origem = data.get("origem") or "cadastro_manual"
        with self._connect(conn) as c:
            cur = c.execute(
                """
                INSERT INTO revisoes
                    (documento_id, revisao, versao, label_revisao, emissao_inicial,
                     data_elaboracao, data_emissao, data_analise,
                     dias_elaboracao, dias_analise,
                     situacao_real, situacao, retorno,
                     emissao_circular, analise_circular, data_circular,
                     ultima_revisao, importacao_id, origem)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["documento_id"],
                    data.get("revisao"),
                    data.get("versao"),
                    data.get("label_revisao"),
                    data.get("emissao_inicial"),
                    data.get("data_elaboracao"),
                    data.get("data_emissao"),
                    data.get("data_analise"),
                    data.get("dias_elaboracao"),
                    data.get("dias_analise"),
                    data.get("situacao_real"),
                    data.get("situacao"),
                    data.get("retorno"),
                    data.get("emissao_circular"),
                    data.get("analise_circular"),
                    data.get("data_circular"),
                    int(data.get("ultima_revisao") or 0),
                    data.get("importacao_id"),
                    origem,
                ),
            )
            return int(cur.lastrowid)

    def atualizar_revisao(
        self,
        revisao_id: int,
        data: dict,
        conn=None,
        coalesce: bool = False,
    ) -> None:
        campos = [c for c in _CAMPOS_ATUALIZAVEIS if c in data]
        if not campos:
            return

        if coalesce:
            sets = ", ".join(f"{c} = COALESCE(?, {c})" for c in campos)
        else:
            sets = ", ".join(f"{c} = ?" for c in campos)

        params = [data[c] for c in campos] + [revisao_id]
        with self._connect(conn) as c:
            c.execute(
                f"UPDATE revisoes SET {sets} WHERE id = ?",
                tuple(params),
            )

    def atualizar_emissao_inicial(
        self, revisao_id: int, emissao_inicial: str, conn=None
    ) -> None:
        with self._connect(conn) as c:
            c.execute(
                "UPDATE revisoes SET emissao_inicial = ? WHERE id = ?",
                (emissao_inicial, revisao_id),
            )

    def desmarcar_ultimas_por_documento(
        self, documento_id: int, conn=None
    ) -> None:
        with self._connect(conn) as c:
            c.execute(
                "UPDATE revisoes SET ultima_revisao = 0 WHERE documento_id = ?",
                (documento_id,),
            )

    def marcar_como_ultima(self, revisao_id: int, conn=None) -> None:
        with self._connect(conn) as c:
            c.execute(
                "UPDATE revisoes SET ultima_revisao = 1 WHERE id = ?",
                (revisao_id,),
            )

    def recalcular_ultimas_por_contrato(
        self, contrato_id: int, conn=None
    ) -> None:
        """Reseta ultima_revisao e marca a mais recente por documento do contrato."""
        with self._connect(conn) as c:
            c.execute(
                """
                UPDATE revisoes SET ultima_revisao = 0
                WHERE documento_id IN (
                    SELECT id FROM documentos WHERE contrato_id = ?
                )
                """,
                (contrato_id,),
            )
            c.execute(
                """
                UPDATE revisoes SET ultima_revisao = 1
                WHERE id IN (
                    SELECT r.id
                    FROM revisoes r
                    JOIN documentos d ON r.documento_id = d.id
                    WHERE d.contrato_id = ?
                      AND r.id = (
                          SELECT r2.id
                          FROM revisoes r2
                          WHERE r2.documento_id = r.documento_id
                          ORDER BY
                              CASE WHEN r2.data_emissao IS NULL THEN 1 ELSE 0 END ASC,
                              r2.data_emissao DESC,
                              r2.id DESC
                          LIMIT 1
                      )
                )
                """,
                (contrato_id,),
            )
