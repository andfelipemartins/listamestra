"""
core/engine/pendencias.py

Deteccao pura de interface das pendencias operacionais do SCLME.

Cada chamada recalcula os sinais a partir das tabelas de origem. Decisoes de
dispensa ficam fora desta engine e sao aplicadas por PendenciasService.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from core.engine.status import carregar_alertas, classificar_status
from core.repositories.documento_repository import DocumentoRepository
from db.connection import get_connection


class TipoPendencia(str, Enum):
    PREVISTO_SEM_INICIO = "previsto_sem_inicio"
    PREVISTO_ESTAGNADO = "previsto_estagnado"
    LISTA_SEM_ID = "lista_sem_id"
    ARQUIVO_SEM_DOCUMENTO = "arquivo_sem_documento"
    DOCUMENTO_SEM_ARQUIVO = "documento_sem_arquivo"
    CODIGO_INVALIDO = "codigo_invalido"
    REVISAO_SEM_DATA = "revisao_sem_data"
    DOCUMENTO_SEM_TITULO = "documento_sem_titulo"
    DIVERGENCIA_TITULO = "divergencia_titulo"
    EMITIDO_SEM_ANALISE = "emitido_sem_analise"
    ANALISE_ATRASADA = "analise_atrasada"


@dataclass(frozen=True)
class Pendencia:
    tipo: TipoPendencia
    chave: str
    codigo: Optional[str] = None
    titulo: Optional[str] = None
    trecho: Optional[str] = None
    disciplina: Optional[str] = None
    mensagem: str = ""
    dias: Optional[int] = None
    documento_id: Optional[int] = None


def _kwargs_conexao(db_path: Optional[str]) -> dict:
    return {"db_path": db_path} if db_path else {}


def _previstos_sem_inicio(
    contrato_id: int,
    db_path: Optional[str],
    conn,
) -> list[Pendencia]:
    rows = DocumentoRepository(db_path).listar_documentos_sem_revisao(
        contrato_id, conn=conn
    )
    return [
        Pendencia(
            tipo=TipoPendencia.PREVISTO_SEM_INICIO,
            chave=str(row["codigo"]),
            codigo=row["codigo"],
            titulo=row.get("titulo"),
            mensagem="Previsto no ID sem revisao iniciada",
        )
        for row in rows
    ]


def _previstos_estagnados(
    contrato_id: int,
    dias_estagnacao: int,
    conn,
) -> list[Pendencia]:
    rows = conn.execute(
        """
        SELECT d.id AS documento_id,
               d.codigo,
               COALESCE(d.titulo, dp.titulo) AS titulo,
               COALESCE(d.trecho, dp.trecho) AS trecho,
               COALESCE(d.disciplina, dp.disciplina) AS disciplina,
               r.situacao,
               r.data_emissao,
               CAST(julianday('now') - julianday(r.criado_em) AS INTEGER) AS dias
        FROM documentos_previstos dp
        JOIN documentos d
          ON d.contrato_id = dp.contrato_id AND d.codigo = dp.codigo
        JOIN revisoes r
          ON r.documento_id = d.id AND r.ultima_revisao = 1
        WHERE dp.contrato_id = ? AND dp.ativo = 1
        ORDER BY d.codigo
        """,
        (contrato_id,),
    ).fetchall()

    pendencias = []
    for row in rows:
        status = classificar_status(row["situacao"], row["data_emissao"])
        dias = row["dias"]
        if status != "Aprovado" and dias is not None and dias > dias_estagnacao:
            pendencias.append(
                Pendencia(
                    tipo=TipoPendencia.PREVISTO_ESTAGNADO,
                    chave=str(row["codigo"]),
                    codigo=row["codigo"],
                    titulo=row["titulo"],
                    trecho=row["trecho"],
                    disciplina=row["disciplina"],
                    mensagem=f"Previsto sem aprovacao ha {dias} dias",
                    dias=int(dias),
                    documento_id=int(row["documento_id"]),
                )
            )
    return pendencias


def _lista_sem_id(contrato_id: int, conn) -> list[Pendencia]:
    # Mantem a consulta de `comparar_id_lista` sem carregar seu contrato DataFrame.
    rows = conn.execute(
        """
        SELECT d.id AS documento_id, d.codigo, d.titulo,
               COALESCE(d.trecho, '00') AS trecho, d.disciplina
        FROM documentos d
        LEFT JOIN documentos_previstos dp
               ON dp.contrato_id = d.contrato_id
              AND dp.codigo = d.codigo
              AND dp.ativo = 1
        WHERE d.contrato_id = ? AND dp.id IS NULL
        ORDER BY d.trecho, d.codigo
        """,
        (contrato_id,),
    ).fetchall()
    return [
        Pendencia(
            tipo=TipoPendencia.LISTA_SEM_ID,
            chave=str(row["codigo"]),
            codigo=row["codigo"],
            titulo=row["titulo"],
            trecho=row["trecho"],
            disciplina=row["disciplina"],
            mensagem="Documento da Lista sem correspondencia ativa no ID",
            documento_id=int(row["documento_id"]),
        )
        for row in rows
    ]


def _arquivos_sem_documento(contrato_id: int, conn) -> list[Pendencia]:
    rows = conn.execute(
        """
        SELECT a.id, a.nome_arquivo
        FROM arquivos a
        JOIN importacoes i ON i.id = a.importacao_id
        WHERE a.documento_id IS NULL AND i.contrato_id = ?
        ORDER BY a.id
        """,
        (contrato_id,),
    ).fetchall()
    return [
        Pendencia(
            tipo=TipoPendencia.ARQUIVO_SEM_DOCUMENTO,
            chave=str(row["id"]),
            mensagem=f"Arquivo sem documento vinculado: {row['nome_arquivo']}",
        )
        for row in rows
    ]


def _documentos_sem_arquivo(contrato_id: int, conn) -> list[Pendencia]:
    rows = conn.execute(
        """
        SELECT d.id AS documento_id, d.codigo, d.titulo, d.trecho, d.disciplina
        FROM documentos d
        LEFT JOIN arquivos a ON a.documento_id = d.id
        WHERE d.contrato_id = ? AND a.id IS NULL
        ORDER BY d.codigo
        """,
        (contrato_id,),
    ).fetchall()
    return [
        Pendencia(
            tipo=TipoPendencia.DOCUMENTO_SEM_ARQUIVO,
            chave=str(row["codigo"]),
            codigo=row["codigo"],
            titulo=row["titulo"],
            trecho=row["trecho"],
            disciplina=row["disciplina"],
            mensagem="Documento sem arquivo vinculado",
            documento_id=int(row["documento_id"]),
        )
        for row in rows
    ]


def _codigos_invalidos(contrato_id: int, conn) -> list[Pendencia]:
    rows = conn.execute(
        """
        SELECT i.id, i.documento_codigo, i.descricao
        FROM inconsistencias i
        JOIN importacoes imp ON imp.id = i.importacao_id
        WHERE imp.contrato_id = ?
          AND i.tipo_inconsistencia = 'codigo_invalido'
          AND i.resolvida = 0
        ORDER BY i.id
        """,
        (contrato_id,),
    ).fetchall()
    return [
        Pendencia(
            tipo=TipoPendencia.CODIGO_INVALIDO,
            chave=str(row["documento_codigo"] or row["id"]),
            codigo=row["documento_codigo"],
            mensagem=row["descricao"] or "Codigo invalido detectado na importacao",
        )
        for row in rows
    ]


def _revisoes_sem_data(contrato_id: int, conn) -> list[Pendencia]:
    rows = conn.execute(
        """
        SELECT d.id AS documento_id, d.codigo, d.titulo, d.trecho, d.disciplina
        FROM revisoes r
        JOIN documentos d ON d.id = r.documento_id
        WHERE d.contrato_id = ?
          AND r.ultima_revisao = 1
          AND r.data_emissao IS NULL
        ORDER BY d.codigo
        """,
        (contrato_id,),
    ).fetchall()
    return [
        Pendencia(
            tipo=TipoPendencia.REVISAO_SEM_DATA,
            chave=str(row["codigo"]),
            codigo=row["codigo"],
            titulo=row["titulo"],
            trecho=row["trecho"],
            disciplina=row["disciplina"],
            mensagem="Ultima revisao sem data de emissao",
            documento_id=int(row["documento_id"]),
        )
        for row in rows
    ]


def _documentos_sem_titulo(contrato_id: int, conn) -> list[Pendencia]:
    rows = conn.execute(
        """
        SELECT id AS documento_id, codigo, titulo, trecho, disciplina
        FROM documentos
        WHERE contrato_id = ? AND (titulo IS NULL OR TRIM(titulo) = '')
        ORDER BY codigo
        """,
        (contrato_id,),
    ).fetchall()
    return [
        Pendencia(
            tipo=TipoPendencia.DOCUMENTO_SEM_TITULO,
            chave=str(row["codigo"]),
            codigo=row["codigo"],
            titulo=row["titulo"],
            trecho=row["trecho"],
            disciplina=row["disciplina"],
            mensagem="Documento sem titulo ou objeto",
            documento_id=int(row["documento_id"]),
        )
        for row in rows
    ]


def _divergencias_titulo(contrato_id: int, conn) -> list[Pendencia]:
    # Mantem a consulta de `comparar_id_lista` sem carregar seu contrato DataFrame.
    rows = conn.execute(
        """
        SELECT d.id AS documento_id,
               dp.codigo,
               COALESCE(dp.trecho, '00') AS trecho,
               COALESCE(d.disciplina, dp.disciplina) AS disciplina,
               dp.titulo AS titulo_id,
               d.titulo AS titulo_lista
        FROM documentos_previstos dp
        JOIN documentos d
          ON d.contrato_id = dp.contrato_id AND d.codigo = dp.codigo
        WHERE dp.contrato_id = ? AND dp.ativo = 1
          AND dp.titulo IS NOT NULL AND dp.titulo != ''
          AND d.titulo IS NOT NULL AND d.titulo != ''
          AND TRIM(dp.titulo) != TRIM(d.titulo)
        ORDER BY dp.trecho, dp.codigo
        """,
        (contrato_id,),
    ).fetchall()
    return [
        Pendencia(
            tipo=TipoPendencia.DIVERGENCIA_TITULO,
            chave=str(row["codigo"]),
            codigo=row["codigo"],
            titulo=row["titulo_lista"],
            trecho=row["trecho"],
            disciplina=row["disciplina"],
            mensagem=(
                f"Titulo do ID: {row['titulo_id']} | "
                f"Titulo da Lista: {row['titulo_lista']}"
            ),
            documento_id=int(row["documento_id"]),
        )
        for row in rows
    ]


def _emitidos_sem_analise(contrato_id: int, conn) -> list[Pendencia]:
    rows = conn.execute(
        """
        SELECT d.id AS documento_id, d.codigo, d.titulo, d.trecho, d.disciplina
        FROM revisoes r
        JOIN documentos d ON d.id = r.documento_id
        WHERE d.contrato_id = ?
          AND r.ultima_revisao = 1
          AND r.data_emissao IS NOT NULL
          AND r.data_analise IS NULL
        ORDER BY d.codigo
        """,
        (contrato_id,),
    ).fetchall()
    return [
        Pendencia(
            tipo=TipoPendencia.EMITIDO_SEM_ANALISE,
            chave=str(row["codigo"]),
            codigo=row["codigo"],
            titulo=row["titulo"],
            trecho=row["trecho"],
            disciplina=row["disciplina"],
            mensagem="Ultima revisao emitida sem data de analise",
            documento_id=int(row["documento_id"]),
        )
        for row in rows
    ]


def _analises_atrasadas(
    contrato_id: int,
    dias_analise: int,
    db_path: Optional[str],
) -> list[Pendencia]:
    alertas = carregar_alertas(contrato_id, dias_analise, db_path)
    return [
        Pendencia(
            tipo=TipoPendencia.ANALISE_ATRASADA,
            chave=str(alerta["codigo"]),
            codigo=alerta["codigo"],
            titulo=alerta.get("titulo"),
            mensagem=alerta["mensagem"],
            dias=alerta.get("dias"),
        )
        for alerta in alertas
        if alerta.get("tipo") == "analise_prolongada"
    ]


def detectar_pendencias(
    contrato_id: int,
    db_path: Optional[str] = None,
    dias_analise: int = 30,
    dias_estagnacao: int = 60,
) -> list[Pendencia]:
    """Recalcula todas as categorias de pendencia para um contrato."""
    if dias_analise < 0 or dias_estagnacao < 0:
        raise ValueError("Os limites de dias nao podem ser negativos.")

    pendencias: list[Pendencia] = []
    with get_connection(**_kwargs_conexao(db_path)) as conn:
        pendencias.extend(_previstos_sem_inicio(contrato_id, db_path, conn))
        pendencias.extend(_previstos_estagnados(contrato_id, dias_estagnacao, conn))
        pendencias.extend(_lista_sem_id(contrato_id, conn))
        pendencias.extend(_arquivos_sem_documento(contrato_id, conn))
        pendencias.extend(_documentos_sem_arquivo(contrato_id, conn))
        pendencias.extend(_codigos_invalidos(contrato_id, conn))
        pendencias.extend(_revisoes_sem_data(contrato_id, conn))
        pendencias.extend(_documentos_sem_titulo(contrato_id, conn))
        pendencias.extend(_divergencias_titulo(contrato_id, conn))
        pendencias.extend(_emitidos_sem_analise(contrato_id, conn))

    pendencias.extend(_analises_atrasadas(contrato_id, dias_analise, db_path))
    return pendencias
