"""
core/repositories/grd_repository.py

Acesso a dados do agregado GRD em lote (remessa).

Tabelas: `grd_remessas` (cabeçalho, com status de ciclo e número único por
contrato) e `grd_itens` (revisões vinculadas + snapshot congelado + cópias por
formato A0–A4/Digital). Aceita conexão externa (`conn`) para participar de
transações abertas.

A tabela legada `grds` (por revisão+setor) NÃO é tocada por este repositório.
"""

from contextlib import contextmanager
from typing import Optional

from db.connection import get_connection

STATUS_GRD = ("rascunho", "emitida", "enviada", "recebida", "cancelada")

# Colunas de cabeçalho atualizáveis via atualizar_status / edição de rascunho.
_CAMPOS_REMESSA_EDITAVEIS = (
    "status", "numero_grd", "data_envio", "setor", "trecho", "modulo",
    "observacoes", "destinatario", "ac", "obra", "emitido_por",
    "recebido_por", "data_recebimento",
)


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
    # Escrita — cabeçalho
    # ------------------------------------------------------------------

    def criar_remessa(self, data: dict, conn=None) -> int:
        """Insere o cabeçalho da GRD e retorna o id criado."""
        if not data.get("contrato_id"):
            raise ValueError("contrato_id e obrigatorio.")
        with self._connect(conn) as c:
            cur = c.execute(
                """
                INSERT INTO grd_remessas
                    (contrato_id, numero_grd, data_envio, setor, trecho, modulo,
                     observacoes, status, destinatario, ac, obra, emitido_por)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["contrato_id"],
                    data.get("numero_grd"),
                    data.get("data_envio"),
                    data.get("setor"),
                    data.get("trecho"),
                    data.get("modulo"),
                    data.get("observacoes"),
                    data.get("status") or "rascunho",
                    data.get("destinatario"),
                    data.get("ac"),
                    data.get("obra"),
                    data.get("emitido_por"),
                ),
            )
            return int(cur.lastrowid)

    def atualizar_status(
        self, grd_id: int, status: str, extra: Optional[dict] = None, conn=None
    ) -> None:
        """Atualiza o status (e campos correlatos como recebido_por/data_recebimento)."""
        if status not in STATUS_GRD:
            raise ValueError(f"status invalido: {status!r}")
        dados = {"status": status, **(extra or {})}
        campos = [k for k in _CAMPOS_REMESSA_EDITAVEIS if k in dados]
        sets = ", ".join(f"{k} = ?" for k in campos)
        params = [dados[k] for k in campos] + [grd_id]
        with self._connect(conn) as c:
            c.execute(f"UPDATE grd_remessas SET {sets} WHERE id = ?", tuple(params))

    # ------------------------------------------------------------------
    # Escrita — itens (com snapshot congelado)
    # ------------------------------------------------------------------

    def adicionar_item(self, grd_id: int, revisao_id: int, conn=None) -> None:
        """Vincula uma revisão (sem snapshot — uso legado/simples)."""
        with self._connect(conn) as c:
            c.execute(
                "INSERT OR IGNORE INTO grd_itens (grd_id, revisao_id) VALUES (?, ?)",
                (grd_id, revisao_id),
            )

    def adicionar_itens(self, grd_id: int, revisao_ids, conn=None) -> int:
        """Vincula várias revisões em lote (sem snapshot). Retorna a quantidade."""
        inseridos = 0
        with self._connect(conn) as c:
            for rid in revisao_ids:
                cur = c.execute(
                    "INSERT OR IGNORE INTO grd_itens (grd_id, revisao_id) VALUES (?, ?)",
                    (grd_id, rid),
                )
                inseridos += cur.rowcount or 0
        return inseridos

    def adicionar_item_snapshot(self, grd_id: int, item: dict, conn=None) -> int:
        """
        Vincula uma revisão à GRD congelando o snapshot do documento e as cópias.

        `item` deve conter `revisao_id` e os campos *_snapshot / qtd_*.
        Retorna 1 se inseriu, 0 se já existia (idempotente por UNIQUE(grd_id, revisao_id)).
        """
        with self._connect(conn) as c:
            cur = c.execute(
                """
                INSERT OR IGNORE INTO grd_itens
                    (grd_id, revisao_id,
                     codigo_snapshot, titulo_snapshot, label_revisao_snapshot,
                     versao_snapshot, situacao_snapshot, data_emissao_snapshot,
                     trecho_snapshot, disciplina_snapshot,
                     qtd_a0, qtd_a1, qtd_a2, qtd_a3, qtd_a4, qtd_digital)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    grd_id, item["revisao_id"],
                    item.get("codigo_snapshot"), item.get("titulo_snapshot"),
                    item.get("label_revisao_snapshot"), item.get("versao_snapshot"),
                    item.get("situacao_snapshot"), item.get("data_emissao_snapshot"),
                    item.get("trecho_snapshot"), item.get("disciplina_snapshot"),
                    int(item.get("qtd_a0") or 0), int(item.get("qtd_a1") or 0),
                    int(item.get("qtd_a2") or 0), int(item.get("qtd_a3") or 0),
                    int(item.get("qtd_a4") or 0), int(item.get("qtd_digital") or 0),
                ),
            )
            return cur.rowcount or 0

    # ------------------------------------------------------------------
    # Leitura
    # ------------------------------------------------------------------

    def numero_existe(
        self, contrato_id: int, numero_grd: str, excluir_id: Optional[int] = None, conn=None
    ) -> bool:
        """True se já há GRD com esse número no contrato (ignora `excluir_id`)."""
        if not numero_grd:
            return False
        sql = "SELECT 1 FROM grd_remessas WHERE contrato_id = ? AND numero_grd = ?"
        params = [contrato_id, numero_grd]
        if excluir_id is not None:
            sql += " AND id != ?"
            params.append(excluir_id)
        with self._connect(conn) as c:
            return c.execute(sql + " LIMIT 1", tuple(params)).fetchone() is not None

    def buscar_por_id(self, grd_id: int, conn=None) -> dict | None:
        with self._connect(conn) as c:
            row = c.execute(
                """
                SELECT g.*,
                       (SELECT COUNT(*) FROM grd_itens i WHERE i.grd_id = g.id) AS total_itens
                FROM grd_remessas g WHERE g.id = ?
                """,
                (grd_id,),
            ).fetchone()
        return dict(row) if row else None

    def buscar_por_numero(self, contrato_id: int, numero_grd: str, conn=None) -> dict | None:
        with self._connect(conn) as c:
            row = c.execute(
                "SELECT * FROM grd_remessas WHERE contrato_id = ? AND numero_grd = ?",
                (contrato_id, numero_grd),
            ).fetchone()
        return dict(row) if row else None

    def listar_remessas(self, contrato_id: int, filtros: Optional[dict] = None, conn=None) -> list[dict]:
        """
        Cabeçalhos das GRDs do contrato com contagem de itens, com filtros opcionais.

        filtros: numero (LIKE), status, data_de/data_ate (data_envio), destinatario
        (LIKE em destinatario/setor), codigo (documento no snapshot dos itens).
        """
        f = filtros or {}
        sql = [
            """
            SELECT g.id, g.numero_grd, g.data_envio, g.setor, g.trecho, g.modulo,
                   g.observacoes, g.status, g.destinatario, g.ac, g.obra,
                   g.emitido_por, g.recebido_por, g.data_recebimento, g.criado_em,
                   (SELECT COUNT(*) FROM grd_itens i WHERE i.grd_id = g.id) AS total_itens
            FROM grd_remessas g
            WHERE g.contrato_id = ?
            """
        ]
        params: list = [contrato_id]
        if f.get("numero"):
            sql.append("AND g.numero_grd LIKE ?"); params.append(f"%{f['numero']}%")
        if f.get("status"):
            sql.append("AND g.status = ?"); params.append(f["status"])
        if f.get("data_de"):
            sql.append("AND g.data_envio >= ?"); params.append(f["data_de"])
        if f.get("data_ate"):
            sql.append("AND g.data_envio <= ?"); params.append(f["data_ate"])
        if f.get("destinatario"):
            sql.append("AND (g.destinatario LIKE ? OR g.setor LIKE ?)")
            params.extend([f"%{f['destinatario']}%", f"%{f['destinatario']}%"])
        if f.get("codigo"):
            sql.append(
                "AND EXISTS (SELECT 1 FROM grd_itens i WHERE i.grd_id = g.id "
                "AND i.codigo_snapshot LIKE ?)"
            )
            params.append(f"%{f['codigo']}%")
        sql.append("ORDER BY g.criado_em DESC, g.id DESC")
        with self._connect(conn) as c:
            rows = c.execute("\n".join(sql), tuple(params)).fetchall()
        return [dict(r) for r in rows]

    def listar_itens(self, grd_id: int, conn=None) -> list[dict]:
        """
        Itens da GRD. Preferência ao snapshot congelado; quando ausente (itens
        legados sem snapshot), cai no JOIN ao vivo com revisoes/documentos.
        """
        with self._connect(conn) as c:
            rows = c.execute(
                """
                SELECT i.id, i.revisao_id,
                       COALESCE(i.codigo_snapshot, d.codigo)              AS codigo,
                       COALESCE(i.titulo_snapshot, d.titulo)             AS titulo,
                       COALESCE(i.label_revisao_snapshot, r.label_revisao) AS label_revisao,
                       COALESCE(i.versao_snapshot, r.versao)             AS versao,
                       COALESCE(i.situacao_snapshot, r.situacao)         AS situacao,
                       COALESCE(i.data_emissao_snapshot, r.data_emissao) AS data_emissao,
                       i.trecho_snapshot, i.disciplina_snapshot,
                       i.qtd_a0, i.qtd_a1, i.qtd_a2, i.qtd_a3, i.qtd_a4, i.qtd_digital
                FROM grd_itens i
                LEFT JOIN revisoes r   ON r.id = i.revisao_id
                LEFT JOIN documentos d ON d.id = r.documento_id
                WHERE i.grd_id = ?
                ORDER BY codigo, label_revisao, versao
                """,
                (grd_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def listar_documentos_para_grd(self, contrato_id: int, conn=None) -> list[dict]:
        """
        Documentos do contrato com a última revisão (elegíveis para compor GRD).

        Apenas documentos com revisão (revisao_id NOT NULL). Retorna o revisao_id
        e os campos necessários para montar o snapshot.
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
