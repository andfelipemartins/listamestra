"""
core/importers/id_importer.py

Importador da aba "ID XX-XX-XXXX" (Índice de Documentos) para o banco SCLME.

Cada linha representa um documento previsto para o contrato — o escopo completo (100%).
Popula a tabela documentos_previstos, que serve de base para calcular o progresso
da Lista de Documentos em relação ao que foi planejado.

A aba tem exatamente 2 colunas:
    Coluna A → CÓDIGO (IDs)
    Coluna B → TÍTULO

O nome da aba varia com a data (ex: "ID 24-04-2026"). O importador detecta
automaticamente a aba cujo nome começa com "ID".

Uso:
    from core.importers.id_importer import IdImporter

    importer = IdImporter()
    resultado = importer.importar("Lista Mestra.xlsx", contrato_id=1)
    print(resultado.novos, resultado.atualizados)
"""

import os
import sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from dataclasses import dataclass, field
from typing import Optional
from db.connection import get_connection
from core.parsers.registry import ParserRegistry

_COL_CODIGO = 0
_COL_TITULO = 1
_HEADER_ROW = 0  # Linha 1 do Excel já tem os cabeçalhos (CÓDIGO / TÍTULO)


@dataclass
class ResultadoImportacaoId:
    importacao_id: int
    total_lidas: int = 0
    novos: int = 0
    atualizados: int = 0
    erros: int = 0
    inconsistencias: list = field(default_factory=list)

    @property
    def total_inconsistencias(self) -> int:
        return len(self.inconsistencias)


class IdImporter:

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path
        self._registry = ParserRegistry()

    def importar(self, arquivo: str, contrato_id: int) -> ResultadoImportacaoId:
        df = self._ler_planilha(arquivo)
        return self._importar_df(df, os.path.basename(arquivo), contrato_id)

    def _ler_planilha(self, arquivo: str) -> pd.DataFrame:
        with pd.ExcelFile(arquivo) as xl:
            sheet = next(
                (s for s in xl.sheet_names if s.strip().upper().startswith("ID")),
                None,
            )
            if sheet is None:
                raise ValueError(
                    f"Nenhuma aba com prefixo 'ID' encontrada em '{os.path.basename(arquivo)}'. "
                    f"Abas disponíveis: {xl.sheet_names}"
                )
            df = xl.parse(sheet_name=sheet, header=_HEADER_ROW)
        if df.shape[1] < 2:
            raise ValueError(
                f"A aba '{sheet}' tem apenas {df.shape[1]} coluna(s). "
                f"São necessárias pelo menos 2 (CÓDIGO e TÍTULO)."
            )
        codigo_col = df.iloc[:, _COL_CODIGO].astype(str).str.strip()
        mask = codigo_col.notna() & (codigo_col != "") & (codigo_col.str.lower() != "nan")
        return df[mask].reset_index(drop=True)

    def _importar_df(self, df: pd.DataFrame, arquivo_nome: str, contrato_id: int) -> ResultadoImportacaoId:
        kwargs = {"db_path": self._db_path} if self._db_path else {}
        with get_connection(**kwargs) as conn:
            imp_id = self._registrar_importacao(conn, contrato_id, arquivo_nome, len(df))
            resultado = ResultadoImportacaoId(importacao_id=imp_id, total_lidas=len(df))
            self._processar_linhas(conn, df, contrato_id, imp_id, resultado)
            self._finalizar_importacao(conn, imp_id, resultado)
        return resultado

    # --- processamento ---

    def _processar_linhas(self, conn, df, contrato_id, imp_id, resultado):
        for _, row in df.iterrows():
            codigo = str(row.iloc[_COL_CODIGO]).strip()
            try:
                self._processar_linha(conn, row, codigo, contrato_id, imp_id, resultado)
            except Exception as exc:
                resultado.erros += 1
                msg = str(exc)
                resultado.inconsistencias.append(
                    {"codigo": codigo, "tipo": "erro_processamento", "descricao": msg}
                )
                self._salvar_inconsistencia(conn, imp_id, codigo, "erro_processamento", msg)

    def _processar_linha(self, conn, row, codigo, contrato_id, imp_id, resultado):
        titulo = self._ler_titulo(row)

        parsed = self._registry.parse(codigo)
        if not parsed.valido:
            resultado.inconsistencias.append(
                {"codigo": codigo, "tipo": "codigo_invalido", "descricao": parsed.mensagem}
            )
            self._salvar_inconsistencia(conn, imp_id, codigo, "codigo_invalido", parsed.mensagem)

        tipo   = parsed.tipo if parsed.valido else None
        trecho = parsed.extras.get("trecho") if parsed.valido else None

        novo = self._upsert_previsto(conn, contrato_id, codigo, titulo, tipo, trecho)
        if novo:
            resultado.novos += 1
        else:
            resultado.atualizados += 1

    # --- upsert ---

    def _upsert_previsto(self, conn, contrato_id, codigo, titulo, tipo, trecho) -> bool:
        row = conn.execute(
            "SELECT id FROM documentos_previstos WHERE contrato_id = ? AND codigo = ?",
            (contrato_id, codigo),
        ).fetchone()
        if row:
            conn.execute(
                """
                UPDATE documentos_previstos SET
                    titulo = COALESCE(?, titulo),
                    tipo   = COALESCE(?, tipo),
                    trecho = COALESCE(?, trecho)
                WHERE id = ?
                """,
                (titulo, tipo, trecho, row["id"]),
            )
            return False
        conn.execute(
            """
            INSERT INTO documentos_previstos
                (contrato_id, codigo, titulo, tipo, trecho, origem)
            VALUES (?, ?, ?, ?, ?, 'importacao_id')
            """,
            (contrato_id, codigo, titulo, tipo, trecho),
        )
        return True

    # --- controle de importação ---

    def _registrar_importacao(self, conn, contrato_id, arquivo, total) -> int:
        cur = conn.execute(
            """
            INSERT INTO importacoes
                (contrato_id, origem, arquivo_importado, total_registros, status)
            VALUES (?, 'id_documentos', ?, ?, 'em_andamento')
            """,
            (contrato_id, arquivo, total),
        )
        return cur.lastrowid

    def _finalizar_importacao(self, conn, imp_id, resultado):
        total_erros = resultado.erros + resultado.total_inconsistencias
        conn.execute(
            """
            UPDATE importacoes SET
                total_erros       = ?,
                total_novos       = ?,
                total_atualizados = ?,
                status            = 'concluido',
                confirmado_em     = datetime('now')
            WHERE id = ?
            """,
            (total_erros, resultado.novos, resultado.atualizados, imp_id),
        )

    def _salvar_inconsistencia(self, conn, imp_id, codigo, tipo, descricao):
        conn.execute(
            """
            INSERT INTO inconsistencias
                (importacao_id, documento_codigo, tipo_inconsistencia, descricao)
            VALUES (?, ?, ?, ?)
            """,
            (imp_id, codigo, tipo, descricao),
        )

    # --- helpers ---

    def _ler_titulo(self, row) -> Optional[str]:
        val = row.iloc[_COL_TITULO]
        try:
            if pd.isna(val):
                return None
        except (TypeError, ValueError):
            pass
        s = str(val).strip()
        return s if s and s.lower() != "nan" else None
