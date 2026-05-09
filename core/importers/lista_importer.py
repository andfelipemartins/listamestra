"""
core/importers/lista_importer.py

Importador da aba "Lista de documentos" (Excel) para o banco SCLME.

Cada linha do Excel representa uma revisão de um documento.
O mesmo CÓDIGO pode aparecer múltiplas vezes (Rev 1, Rev 2, ...).

Uso:
    from core.importers.lista_importer import ListaImporter

    importer = ListaImporter()
    resultado = importer.importar("Lista Mestra.xlsx", contrato_id=1)
    print(resultado.novos_documentos, resultado.novas_revisoes)
"""

import os
import sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from dataclasses import dataclass, field
from typing import Optional
from db.connection import get_connection
from core.parsers.registry import ParserRegistry

# Posições das colunas (índice 0) na aba "Lista de documentos"
# A planilha tem dois níveis de cabeçalho: linha 1 = grupos (ALYA, METRÔ...),
# linha 2 = nomes reais das colunas. Lemos com header=1 (pandas) = Excel linha 2.
# Como há nomes duplicados (GRD, DATA ENVIO, SITUAÇÃO...), o acesso é sempre por posição.
_COL = {
    "item":            0,
    "sigla":           1,
    "linha":           2,
    "trecho":          3,
    "subtrecho":       4,
    "unidade":         5,
    "etapa":           6,
    "classe_sub":      7,
    "sequencial":      8,
    "codigo":          9,
    "revisao":         10,
    "versao":          11,
    "nome_trecho":     12,
    "emissao_inicial": 13,
    "ultima_rev_data": 14,
    "elaboracao":      15,
    "modalidade":      16,
    "etapa2":          17,
    "estrutura":       18,
    "descricao":       19,
    "fase":            20,
    "data_elaboracao": 21,
    "data_emissao":    22,
    "dias_elaboracao": 23,
    "emissao":         24,
    "data_analise":    25,
    "dias_analise":    26,
    "situacao_real":   27,
    "situacao":        28,
    "retorno":         29,
    "analise_interna": 30,
    "data_circular":   31,
    "num_circular":    32,
}

_SHEET_NAMES = ["Lista de documentos", "Planilha1"]
_HEADER_ROW = 1  # Excel linha 2 tem os nomes das colunas


@dataclass
class ResultadoImportacao:
    importacao_id: int
    total_lidas: int = 0
    novos_documentos: int = 0
    documentos_atualizados: int = 0
    novas_revisoes: int = 0
    revisoes_atualizadas: int = 0
    erros: int = 0
    inconsistencias: list = field(default_factory=list)

    @property
    def total_documentos(self) -> int:
        return self.novos_documentos + self.documentos_atualizados

    @property
    def total_revisoes(self) -> int:
        return self.novas_revisoes + self.revisoes_atualizadas


class ListaImporter:

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path
        self._registry = ParserRegistry()

    def importar(self, arquivo: str, contrato_id: int) -> ResultadoImportacao:
        df = self._ler_planilha(arquivo)
        return self._importar_df(df, os.path.basename(arquivo), contrato_id)

    def _ler_planilha(self, arquivo: str) -> pd.DataFrame:
        xl = pd.ExcelFile(arquivo)
        sheet = next((s for s in _SHEET_NAMES if s in xl.sheet_names), xl.sheet_names[0])
        df = pd.read_excel(arquivo, sheet_name=sheet, header=_HEADER_ROW)
        codigo_col = df.iloc[:, _COL["codigo"]].astype(str).str.strip()
        mask = codigo_col.notna() & (codigo_col != "") & (codigo_col.str.lower() != "nan")
        return df[mask].reset_index(drop=True)

    def _importar_df(self, df: pd.DataFrame, arquivo_nome: str, contrato_id: int) -> ResultadoImportacao:
        kwargs = {"db_path": self._db_path} if self._db_path else {}
        with get_connection(**kwargs) as conn:
            imp_id = self._registrar_importacao(conn, contrato_id, arquivo_nome, len(df))
            resultado = ResultadoImportacao(importacao_id=imp_id, total_lidas=len(df))
            self._processar_linhas(conn, df, contrato_id, imp_id, resultado)
            self._marcar_ultimas_revisoes(conn, contrato_id)
            self._finalizar_importacao(conn, imp_id, resultado)
        return resultado

    # --- processamento linha a linha ---

    def _processar_linhas(self, conn, df, contrato_id, imp_id, resultado):
        for _, row in df.iterrows():
            codigo = str(row.iloc[_COL["codigo"]]).strip()
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
        parsed = self._registry.parse(codigo)
        if not parsed.valido:
            resultado.inconsistencias.append(
                {"codigo": codigo, "tipo": "codigo_invalido", "descricao": parsed.mensagem}
            )
            self._salvar_inconsistencia(conn, imp_id, codigo, "codigo_invalido", parsed.mensagem)

        doc_data = {
            "contrato_id": contrato_id,
            "codigo": codigo,
            "tipo": self._str(row, "sigla") or (parsed.tipo if parsed.valido else None),
            "titulo": self._str(row, "descricao"),
            "disciplina": self._str(row, "estrutura"),
            "modalidade": self._str(row, "modalidade"),
            "trecho": self._trecho(row),
            "nome_trecho": self._str(row, "nome_trecho"),
            "responsavel": self._str(row, "elaboracao"),
        }

        doc_id, novo = self._upsert_documento(conn, doc_data)
        if novo:
            resultado.novos_documentos += 1
        else:
            resultado.documentos_atualizados += 1

        revisao_num = self._int(row, "revisao", 0)
        rev_data = {
            "documento_id": doc_id,
            "revisao": revisao_num,
            "versao": self._int(row, "versao", 1),
            "label_revisao": f"Rev{revisao_num}",
            "data_elaboracao": self._data(row, "data_elaboracao"),
            "data_emissao": self._data(row, "data_emissao"),
            "data_analise": self._data(row, "data_analise"),
            "dias_elaboracao": self._int(row, "dias_elaboracao"),
            "dias_analise": self._int(row, "dias_analise"),
            "situacao_real": self._str(row, "situacao_real"),
            "situacao": self._str(row, "situacao"),
            "retorno": self._str(row, "retorno"),
            "emissao_circular": self._str(row, "num_circular"),
            "analise_circular": self._str(row, "analise_interna"),
            "importacao_id": imp_id,
        }

        rev_nova = self._upsert_revisao(conn, rev_data)
        if rev_nova:
            resultado.novas_revisoes += 1
        else:
            resultado.revisoes_atualizadas += 1

    # --- upserts ---

    def _upsert_documento(self, conn, data) -> tuple[int, bool]:
        row = conn.execute(
            "SELECT id FROM documentos WHERE contrato_id = ? AND codigo = ?",
            (data["contrato_id"], data["codigo"]),
        ).fetchone()
        if row:
            conn.execute(
                """
                UPDATE documentos SET
                    tipo         = COALESCE(?, tipo),
                    titulo       = COALESCE(?, titulo),
                    disciplina   = COALESCE(?, disciplina),
                    modalidade   = COALESCE(?, modalidade),
                    trecho       = COALESCE(?, trecho),
                    nome_trecho  = COALESCE(?, nome_trecho),
                    responsavel  = COALESCE(?, responsavel),
                    atualizado_em = datetime('now')
                WHERE id = ?
                """,
                (
                    data["tipo"], data["titulo"], data["disciplina"],
                    data["modalidade"], data["trecho"], data["nome_trecho"],
                    data["responsavel"], row["id"],
                ),
            )
            return row["id"], False

        cur = conn.execute(
            """
            INSERT INTO documentos
                (contrato_id, codigo, tipo, titulo, disciplina, modalidade,
                 trecho, nome_trecho, responsavel, origem)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'importacao_lista')
            """,
            (
                data["contrato_id"], data["codigo"], data["tipo"], data["titulo"],
                data["disciplina"], data["modalidade"], data["trecho"],
                data["nome_trecho"], data["responsavel"],
            ),
        )
        return cur.lastrowid, True

    def _upsert_revisao(self, conn, data) -> bool:
        row = conn.execute(
            "SELECT id FROM revisoes WHERE documento_id = ? AND revisao = ? AND versao = ?",
            (data["documento_id"], data["revisao"], data["versao"]),
        ).fetchone()
        if row:
            conn.execute(
                """
                UPDATE revisoes SET
                    label_revisao    = COALESCE(?, label_revisao),
                    data_elaboracao  = COALESCE(?, data_elaboracao),
                    data_emissao     = COALESCE(?, data_emissao),
                    data_analise     = COALESCE(?, data_analise),
                    dias_elaboracao  = COALESCE(?, dias_elaboracao),
                    dias_analise     = COALESCE(?, dias_analise),
                    situacao_real    = COALESCE(?, situacao_real),
                    situacao         = COALESCE(?, situacao),
                    retorno          = COALESCE(?, retorno),
                    emissao_circular = COALESCE(?, emissao_circular),
                    analise_circular = COALESCE(?, analise_circular)
                WHERE id = ?
                """,
                (
                    data["label_revisao"], data["data_elaboracao"], data["data_emissao"],
                    data["data_analise"], data["dias_elaboracao"], data["dias_analise"],
                    data["situacao_real"], data["situacao"], data["retorno"],
                    data["emissao_circular"], data["analise_circular"], row["id"],
                ),
            )
            return False

        conn.execute(
            """
            INSERT INTO revisoes
                (documento_id, revisao, versao, label_revisao,
                 data_elaboracao, data_emissao, data_analise,
                 dias_elaboracao, dias_analise,
                 situacao_real, situacao, retorno,
                 emissao_circular, analise_circular,
                 ultima_revisao, importacao_id, origem)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 'importacao_lista')
            """,
            (
                data["documento_id"], data["revisao"], data["versao"], data["label_revisao"],
                data["data_elaboracao"], data["data_emissao"], data["data_analise"],
                data["dias_elaboracao"], data["dias_analise"],
                data["situacao_real"], data["situacao"], data["retorno"],
                data["emissao_circular"], data["analise_circular"],
                data["importacao_id"],
            ),
        )
        return True

    def _marcar_ultimas_revisoes(self, conn, contrato_id):
        conn.execute(
            """
            UPDATE revisoes SET ultima_revisao = 0
            WHERE documento_id IN (SELECT id FROM documentos WHERE contrato_id = ?)
            """,
            (contrato_id,),
        )
        conn.execute(
            """
            UPDATE revisoes SET ultima_revisao = 1
            WHERE id IN (
                SELECT r.id FROM revisoes r
                JOIN documentos d ON r.documento_id = d.id
                WHERE d.contrato_id = ?
                  AND r.revisao = (
                      SELECT MAX(r2.revisao) FROM revisoes r2
                      WHERE r2.documento_id = r.documento_id
                  )
                  AND r.versao = (
                      SELECT MAX(r3.versao) FROM revisoes r3
                      WHERE r3.documento_id = r.documento_id
                        AND r3.revisao = r.revisao
                  )
            )
            """,
            (contrato_id,),
        )

    # --- controle de importação ---

    def _registrar_importacao(self, conn, contrato_id, arquivo, total) -> int:
        cur = conn.execute(
            """
            INSERT INTO importacoes
                (contrato_id, origem, arquivo_importado, total_registros, status)
            VALUES (?, 'lista_documentos', ?, ?, 'em_andamento')
            """,
            (contrato_id, arquivo, total),
        )
        return cur.lastrowid

    def _finalizar_importacao(self, conn, imp_id, resultado):
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
            (resultado.erros, resultado.novos_documentos, resultado.documentos_atualizados, imp_id),
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

    # --- extração de valores do DataFrame ---

    def _str(self, row, key) -> Optional[str]:
        val = row.iloc[_COL[key]]
        try:
            if pd.isna(val):
                return None
        except (TypeError, ValueError):
            pass
        s = str(val).strip()
        return s if s and s.lower() != "nan" else None

    def _int(self, row, key, default=None) -> Optional[int]:
        val = row.iloc[_COL[key]]
        try:
            if pd.isna(val):
                return default
        except (TypeError, ValueError):
            pass
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return default

    def _data(self, row, key) -> Optional[str]:
        val = row.iloc[_COL[key]]
        try:
            if pd.isna(val):
                return None
        except (TypeError, ValueError):
            pass
        if isinstance(val, pd.Timestamp):
            return val.date().isoformat()
        s = str(val).strip()
        return s if s and s.lower() not in ("nat", "nan") else None

    def _trecho(self, row) -> Optional[str]:
        val = row.iloc[_COL["trecho"]]
        try:
            if pd.isna(val):
                return None
        except (TypeError, ValueError):
            pass
        try:
            return str(int(float(val))).zfill(2)
        except (ValueError, TypeError):
            s = str(val).strip()
            return s or None
