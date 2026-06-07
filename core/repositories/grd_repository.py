"""
core/repositories/grd_repository.py

Acesso a dados do agregado GRD em lote (remessa).

Concentra o SQL das tabelas `grd_remessas` (cabeçalho) e `grd_itens` (revisões
vinculadas), mantendo páginas e serviços livres de consultas diretas. Aceita
uma conexão externa (`conn`) para participar de transações já abertas.

A tabela legada `grds` (por revisão+setor) NÃO é tocada por este repositório.
"""

from contextlib import contextmanager
from typing import Optional

from db.connection import get_connection


class GrdRepository:
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
    # Escrita
    # ------------------------------------------------------------------

    def criar_remessa(self, data: dict, conn=None) -> int:
        """Insere o cabeçalho da GRD e retorna o id criado."""
        if not data.get("contrato_id"):
            raise ValueError("contrato_id e obrigatorio.")
        with self._connect(conn) as c:
            cur = c.execute(
                """
                INSERT INTO grd_remessas
                    (contrato_id, numero_grd, data_envio, setor, trecho, modulo, observacoes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["contrato_id"],
                    data.get("numero_grd"),
                    data.get("data_envio"),
                    data.get("setor"),
                    data.get("trecho"),
                    data.get("modulo"),
                    data.get("observacoes"),
                ),
            )
            return int(cur.lastrowid)

    def adicionar_item(self, grd_id: int, revisao_id: int, conn=None) -> None:
        """Vincula uma revisão à GRD (idempotente por UNIQUE(grd_id, revisao_id))."""
        with self._connect(conn) as c:
            c.execute(
                """
                INSERT OR IGNORE INTO grd_itens (grd_id, revisao_id)
                VALUES (?, ?)
                """,
                (grd_id, revisao_id),
            )

    def adicionar_itens(self, grd_id: int, revisao_ids, conn=None) -> int:
        """Vincula várias revisões em lote. Retorna a quantidade inserida."""
        inseridos = 0
        with self._connect(conn) as c:
            for rid in revisao_ids:
                cur = c.execute(
                    "INSERT OR IGNORE INTO grd_itens (grd_id, revisao_id) VALUES (?, ?)",
                    (grd_id, rid),
                )
                inseridos += cur.rowcount or 0
        return inseridos

    # ------------------------------------------------------------------
    # Leitura
    # ------------------------------------------------------------------

    def listar_remessas(self, contrato_id: int, conn=None) -> list[dict]:
        """Cabeçalhos das GRDs do contrato com a contagem de itens."""
        with self._connect(conn) as c:
            rows = c.execute(
                """
                SELECT g.id, g.numero_grd, g.data_envio, g.setor, g.trecho,
                       g.modulo, g.observacoes, g.criado_em,
                       (SELECT COUNT(*) FROM grd_itens i WHERE i.grd_id = g.id) AS total_itens
                FROM grd_remessas g
                WHERE g.contrato_id = ?
                ORDER BY g.criado_em DESC, g.id DESC
                """,
                (contrato_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def listar_itens(self, grd_id: int, conn=None) -> list[dict]:
        """Revisões vinculadas a uma GRD, com dados do documento."""
        with self._connect(conn) as c:
            rows = c.execute(
                """
                SELECT i.id, i.revisao_id, d.codigo, d.titulo,
                       r.label_revisao, r.versao, r.situacao, r.data_emissao
                FROM grd_itens i
                JOIN revisoes r   ON r.id = i.revisao_id
                JOIN documentos d ON d.id = r.documento_id
                WHERE i.grd_id = ?
                ORDER BY d.codigo, r.label_revisao, r.versao
                """,
                (grd_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def listar_documentos_para_grd(self, contrato_id: int, conn=None) -> list[dict]:
        """
        Documentos do contrato com a última revisão (elegíveis para compor GRD).

        Apenas documentos que possuem revisão (revisao_id NOT NULL) — não se remete
        documento sem revisão emitida. Retorna o revisao_id da última revisão.
        """
        with self._connect(conn) as c:
            rows = c.execute(
                """
                SELECT d.id AS documento_id, d.codigo, d.titulo, d.tipo,
                       COALESCE(d.trecho, '00') AS trecho, d.disciplina,
                       r.id AS revisao_id, r.label_revisao, r.versao,
                       r.situacao, r.data_emissao
                FROM documentos d
                JOIN revisoes r ON r.documento_id = d.id AND r.ultima_revisao = 1
                WHERE d.contrato_id = ?
                ORDER BY d.trecho, d.codigo
                """,
                (contrato_id,),
            ).fetchall()
        return [dict(r) for r in rows]
