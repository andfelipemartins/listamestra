"""
core/repositories/documento_repository.py

Acesso a dados de documentos.

Concentra SQL da tabela documentos para manter paginas Streamlit, engines e
importers livres de consultas diretas. Aceita uma conexao externa (`conn`)
para participar de transacoes ja abertas (importers, cadastro manual).
"""

from contextlib import contextmanager
from typing import Optional

from db.connection import get_connection


_CAMPOS_ATUALIZAVEIS = (
    "tipo",
    "titulo",
    "disciplina",
    "modalidade",
    "trecho",
    "nome_trecho",
    "responsavel",
    "fase",
    "observacoes",
    "origem",
)


class DocumentoRepository:
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

    def buscar_por_id(self, documento_id: int, conn=None) -> dict | None:
        with self._connect(conn) as c:
            row = c.execute(
                "SELECT * FROM documentos WHERE id = ?",
                (documento_id,),
            ).fetchone()
        return dict(row) if row else None

    def buscar_por_codigo(
        self, contrato_id: int, codigo: str, conn=None
    ) -> dict | None:
        with self._connect(conn) as c:
            row = c.execute(
                "SELECT * FROM documentos WHERE contrato_id = ? AND codigo = ?",
                (contrato_id, codigo),
            ).fetchone()
        return dict(row) if row else None

    def buscar_id_por_codigo(
        self, contrato_id: int, codigo: str, conn=None
    ) -> int | None:
        with self._connect(conn) as c:
            row = c.execute(
                "SELECT id FROM documentos WHERE contrato_id = ? AND codigo = ?",
                (contrato_id, codigo),
            ).fetchone()
        return int(row["id"]) if row else None

    def existe_documento(
        self, contrato_id: int, codigo: str, conn=None
    ) -> bool:
        return self.buscar_id_por_codigo(contrato_id, codigo, conn) is not None

    def listar_por_contrato(self, contrato_id: int, conn=None) -> list[dict]:
        with self._connect(conn) as c:
            rows = c.execute(
                """
                SELECT id, contrato_id, codigo, tipo, titulo, disciplina, modalidade,
                       trecho, nome_trecho, responsavel, fase, origem, observacoes,
                       criado_em, atualizado_em
                FROM documentos
                WHERE contrato_id = ?
                ORDER BY trecho, codigo
                """,
                (contrato_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def listar_codigos_por_contrato(
        self, contrato_id: int, conn=None
    ) -> list[str]:
        with self._connect(conn) as c:
            rows = c.execute(
                "SELECT codigo FROM documentos WHERE contrato_id = ? ORDER BY codigo",
                (contrato_id,),
            ).fetchall()
        return [r["codigo"] for r in rows]

    def listar_ids_por_contrato(
        self, contrato_id: int, conn=None
    ) -> list[int]:
        with self._connect(conn) as c:
            rows = c.execute(
                "SELECT id FROM documentos WHERE contrato_id = ?",
                (contrato_id,),
            ).fetchall()
        return [int(r["id"]) for r in rows]

    def listar_com_ultima_revisao(
        self, contrato_id: int, conn=None
    ) -> list[dict]:
        """Documentos do contrato com colunas de leitura da ultima revisao.

        Suporta a pagina Documento sem expor o JOIN nas paginas.
        """
        with self._connect(conn) as c:
            rows = c.execute(
                """
                SELECT d.id, d.codigo, d.titulo, d.tipo, d.trecho,
                       d.modalidade, d.disciplina, d.contrato_id,
                       r.situacao, r.data_emissao
                FROM documentos d
                LEFT JOIN revisoes r
                       ON r.documento_id = d.id AND r.ultima_revisao = 1
                WHERE d.contrato_id = ?
                ORDER BY d.trecho, d.codigo
                """,
                (contrato_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def listar_documentos_sem_revisao(
        self, contrato_id: int, conn=None
    ) -> list[dict]:
        """Previstos no ID, presentes em documentos, mas sem nenhuma revisao.

        Usado pelo motor de alertas (engine/status.carregar_alertas).
        """
        with self._connect(conn) as c:
            rows = c.execute(
                """
                SELECT dp.codigo, COALESCE(dp.titulo, '') AS titulo
                FROM documentos_previstos dp
                LEFT JOIN documentos d
                       ON d.contrato_id = dp.contrato_id AND d.codigo = dp.codigo
                LEFT JOIN revisoes r ON r.documento_id = d.id
                WHERE dp.contrato_id = ? AND dp.ativo = 1 AND r.id IS NULL
                """,
                (contrato_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def buscar_previsto(
        self, contrato_id: int, codigo: str, conn=None
    ) -> dict | None:
        """Retorna titulo, tipo, disciplina e trecho do escopo previsto do ID."""
        with self._connect(conn) as c:
            row = c.execute(
                """
                SELECT titulo, tipo, disciplina, trecho
                FROM documentos_previstos
                WHERE contrato_id = ? AND codigo = ? AND ativo = 1
                """,
                (contrato_id, codigo),
            ).fetchone()
        return dict(row) if row else None

    def buscar_documento_com_titulo_previsto(
        self, contrato_id: int, codigo: str, conn=None
    ) -> dict | None:
        """Retorna id e titulo (com fallback para o titulo do ID) de um documento.

        Mantem o helper usado pelo preview de arquivos centralizado.
        """
        with self._connect(conn) as c:
            row = c.execute(
                """
                SELECT d.id,
                       COALESCE(d.titulo, dp.titulo) AS titulo
                FROM documentos d
                LEFT JOIN documentos_previstos dp
                       ON dp.contrato_id = d.contrato_id AND dp.codigo = d.codigo
                WHERE d.contrato_id = ? AND d.codigo = ?
                """,
                (contrato_id, codigo),
            ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Contagem
    # ------------------------------------------------------------------

    def contar_por_contrato(self, contrato_id: int, conn=None) -> int:
        with self._connect(conn) as c:
            row = c.execute(
                "SELECT COUNT(*) AS total FROM documentos WHERE contrato_id = ?",
                (contrato_id,),
            ).fetchone()
        return int(row["total"])

    def contar_previstos_por_contrato(
        self, contrato_id: int, conn=None
    ) -> int:
        with self._connect(conn) as c:
            row = c.execute(
                """
                SELECT COUNT(*) AS total
                FROM documentos_previstos
                WHERE contrato_id = ? AND ativo = 1
                """,
                (contrato_id,),
            ).fetchone()
        return int(row["total"])

    # ------------------------------------------------------------------
    # Escrita
    # ------------------------------------------------------------------

    def criar_documento(self, data: dict, conn=None) -> int:
        """Insere um novo documento e retorna o id.

        Campos obrigatorios: contrato_id, codigo. Os demais aceitam None.
        """
        if "contrato_id" not in data or "codigo" not in data:
            raise ValueError("contrato_id e codigo sao obrigatorios.")

        origem = data.get("origem") or "cadastro_manual"
        with self._connect(conn) as c:
            cur = c.execute(
                """
                INSERT INTO documentos
                    (contrato_id, codigo, tipo, titulo, disciplina, modalidade,
                     trecho, nome_trecho, responsavel, fase, observacoes, origem)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["contrato_id"],
                    data["codigo"],
                    data.get("tipo"),
                    data.get("titulo"),
                    data.get("disciplina"),
                    data.get("modalidade"),
                    data.get("trecho"),
                    data.get("nome_trecho"),
                    data.get("responsavel"),
                    data.get("fase"),
                    data.get("observacoes"),
                    origem,
                ),
            )
            return int(cur.lastrowid)

    def atualizar_documento(
        self,
        documento_id: int,
        data: dict,
        conn=None,
        coalesce: bool = False,
    ) -> None:
        """Atualiza colunas do documento.

        coalesce=True usa COALESCE(?, coluna), preservando valores existentes
        para campos None. Quando False, sobrescreve com NULL se enviado.
        """
        campos = [c for c in _CAMPOS_ATUALIZAVEIS if c in data]
        if not campos:
            return

        if coalesce:
            sets = ", ".join(f"{c} = COALESCE(?, {c})" for c in campos)
        else:
            sets = ", ".join(f"{c} = ?" for c in campos)
        sets += ", atualizado_em = datetime('now')"

        params = [data[c] for c in campos] + [documento_id]
        with self._connect(conn) as c:
            c.execute(
                f"UPDATE documentos SET {sets} WHERE id = ?",
                tuple(params),
            )

    def atualizar_titulo(
        self, documento_id: int, titulo: str, conn=None
    ) -> None:
        with self._connect(conn) as c:
            c.execute(
                "UPDATE documentos SET titulo = ?, atualizado_em = datetime('now') WHERE id = ?",
                (titulo, documento_id),
            )
