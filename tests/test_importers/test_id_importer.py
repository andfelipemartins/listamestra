"""
tests/test_importers/test_id_importer.py

Testes do importador do Índice de Documentos (ID) para documentos_previstos.

Execute com:
    pytest tests/ -v
"""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from core.importers.id_importer import IdImporter, ResultadoImportacaoId
from db.connection import get_connection

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scripts"))
from init_db import init_db


# ---------------------------------------------------------------------------
# Helpers de fixture
# ---------------------------------------------------------------------------

def _linha(codigo: str, titulo: str = "Documento de teste") -> list:
    return [codigo, titulo]


def _df(*linhas: list) -> pd.DataFrame:
    return pd.DataFrame(list(linhas))


# ---------------------------------------------------------------------------
# Fixture de banco temporário
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "test_sclme.db")
    init_db(db_path, verbose=False)
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO contratos (nome, cliente) VALUES ('Contrato Teste', 'Metrô SP')"
        )
        contrato_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return db_path, contrato_id


@pytest.fixture
def importer(db):
    db_path, _ = db
    return IdImporter(db_path=db_path)


# ---------------------------------------------------------------------------
# Testes de importação básica
# ---------------------------------------------------------------------------

class TestImportacaoBasica:

    def test_importa_documento_simples(self, db, importer):
        db_path, contrato_id = db
        resultado = importer._importar_df(
            _df(_linha("RT-15.25.00.00-6A1-1001", "Relatório Técnico de Metodologia")),
            "ID 24-04-2026.xlsx", contrato_id,
        )

        assert resultado.novos == 1
        assert resultado.atualizados == 0
        assert resultado.erros == 0
        assert resultado.total_lidas == 1

        with get_connection(db_path) as conn:
            prev = conn.execute(
                "SELECT * FROM documentos_previstos WHERE codigo = ?",
                ("RT-15.25.00.00-6A1-1001",),
            ).fetchone()

        assert prev is not None
        assert prev["titulo"] == "Relatório Técnico de Metodologia"
        assert prev["tipo"] == "RT"
        assert prev["trecho"] == "25"
        assert prev["origem"] == "importacao_id"

    def test_importa_multiplos_documentos(self, db, importer):
        db_path, contrato_id = db
        resultado = importer._importar_df(
            _df(
                _linha("RT-15.25.00.00-6A1-1001", "Relatório Técnico"),
                _linha("DE-15.25.00.00-6A1-1001", "Desenho de Planta"),
                _linha("ID-15.25.00.00-6A9-1001", "Índice de Documentos - Civil"),
                _linha("LM-15.23.17.84-6B3-1001", "Lista de Materiais"),
            ),
            "test.xlsx", contrato_id,
        )

        assert resultado.novos == 4
        assert resultado.total_lidas == 4

        with get_connection(db_path) as conn:
            total = conn.execute(
                "SELECT COUNT(*) AS n FROM documentos_previstos WHERE contrato_id = ?",
                (contrato_id,),
            ).fetchone()["n"]
        assert total == 4

    def test_tipo_extraido_do_parser(self, db, importer):
        db_path, contrato_id = db
        importer._importar_df(
            _df(
                _linha("DE-15.23.17.84-6B3-1001", "Desenho"),
                _linha("MC-15.25.00.00-6A1-1001", "Memorial de Cálculo"),
                _linha("MD-15.25.00.00-6A1-1001", "Memorial Descritivo"),
            ),
            "test.xlsx", contrato_id,
        )

        with get_connection(db_path) as conn:
            tipos = {
                row["codigo"]: row["tipo"]
                for row in conn.execute(
                    "SELECT codigo, tipo FROM documentos_previstos"
                ).fetchall()
            }

        assert tipos["DE-15.23.17.84-6B3-1001"] == "DE"
        assert tipos["MC-15.25.00.00-6A1-1001"] == "MC"
        assert tipos["MD-15.25.00.00-6A1-1001"] == "MD"

    def test_trecho_extraido_do_parser(self, db, importer):
        db_path, contrato_id = db
        importer._importar_df(
            _df(
                _linha("DE-15.23.17.84-6B3-1001"),  # trecho 23 = São Mateus
                _linha("DE-15.25.00.00-6A1-1001"),  # trecho 25 = Ragueb Chohfi
                _linha("PE-15.00.00.00-6A9-1002"),  # trecho 00 = Geral
            ),
            "test.xlsx", contrato_id,
        )

        with get_connection(db_path) as conn:
            trechos = {
                row["codigo"]: row["trecho"]
                for row in conn.execute(
                    "SELECT codigo, trecho FROM documentos_previstos"
                ).fetchall()
            }

        assert trechos["DE-15.23.17.84-6B3-1001"] == "23"
        assert trechos["DE-15.25.00.00-6A1-1001"] == "25"
        assert trechos["PE-15.00.00.00-6A9-1002"] == "00"

    def test_ativo_padrao_verdadeiro(self, db, importer):
        db_path, contrato_id = db
        importer._importar_df(
            _df(_linha("DE-15.25.00.00-6A1-1001")),
            "test.xlsx", contrato_id,
        )

        with get_connection(db_path) as conn:
            prev = conn.execute(
                "SELECT ativo FROM documentos_previstos WHERE codigo = ?",
                ("DE-15.25.00.00-6A1-1001",),
            ).fetchone()
        assert prev["ativo"] == 1


# ---------------------------------------------------------------------------
# Testes de reimportação (idempotência)
# ---------------------------------------------------------------------------

class TestReimportacao:

    def test_reimportacao_nao_duplica(self, db, importer):
        db_path, contrato_id = db
        df = _df(_linha("DE-15.25.00.00-6A1-1001", "Desenho"))
        importer._importar_df(df, "test.xlsx", contrato_id)
        importer._importar_df(df, "test.xlsx", contrato_id)

        with get_connection(db_path) as conn:
            n = conn.execute(
                "SELECT COUNT(*) AS n FROM documentos_previstos WHERE codigo = ?",
                ("DE-15.25.00.00-6A1-1001",),
            ).fetchone()["n"]
        assert n == 1

    def test_segunda_importacao_conta_como_atualizado(self, db, importer):
        db_path, contrato_id = db
        df = _df(_linha("DE-15.25.00.00-6A1-1001", "Desenho"))
        importer._importar_df(df, "test.xlsx", contrato_id)
        resultado2 = importer._importar_df(df, "test.xlsx", contrato_id)

        assert resultado2.novos == 0
        assert resultado2.atualizados == 1

    def test_reimportacao_atualiza_titulo(self, db, importer):
        db_path, contrato_id = db
        importer._importar_df(
            _df(_linha("DE-15.25.00.00-6A1-1001", "Título antigo")),
            "v1.xlsx", contrato_id,
        )
        importer._importar_df(
            _df(_linha("DE-15.25.00.00-6A1-1001", "Título corrigido")),
            "v2.xlsx", contrato_id,
        )

        with get_connection(db_path) as conn:
            prev = conn.execute(
                "SELECT titulo FROM documentos_previstos WHERE codigo = ?",
                ("DE-15.25.00.00-6A1-1001",),
            ).fetchone()
        assert prev["titulo"] == "Título corrigido"


# ---------------------------------------------------------------------------
# Testes de inconsistências
# ---------------------------------------------------------------------------

class TestInconsistencias:

    def test_codigo_invalido_registra_inconsistencia(self, db, importer):
        db_path, contrato_id = db
        resultado = importer._importar_df(
            _df(_linha("CODIGO_INVALIDO", "Título qualquer")),
            "test.xlsx", contrato_id,
        )

        assert resultado.total_inconsistencias >= 1
        assert any(i["tipo"] == "codigo_invalido" for i in resultado.inconsistencias)

        with get_connection(db_path) as conn:
            incs = conn.execute("SELECT * FROM inconsistencias").fetchall()
        assert len(incs) >= 1

    def test_codigo_invalido_nao_impede_demais_linhas(self, db, importer):
        db_path, contrato_id = db
        resultado = importer._importar_df(
            _df(
                _linha("INVALIDO", "Inválido"),
                _linha("DE-15.25.00.00-6A1-1001", "Válido"),
            ),
            "test.xlsx", contrato_id,
        )

        assert resultado.total_lidas == 2
        # Ambos são inseridos (código inválido mantém rastreabilidade)
        with get_connection(db_path) as conn:
            total = conn.execute(
                "SELECT COUNT(*) AS n FROM documentos_previstos"
            ).fetchone()["n"]
        assert total == 2


# ---------------------------------------------------------------------------
# Testes da tabela importacoes
# ---------------------------------------------------------------------------

class TestRegistroImportacao:

    def test_importacao_registrada(self, db, importer):
        db_path, contrato_id = db
        resultado = importer._importar_df(
            _df(_linha("DE-15.25.00.00-6A1-1001")),
            "ID 24-04-2026.xlsx", contrato_id,
        )

        with get_connection(db_path) as conn:
            imp = conn.execute(
                "SELECT * FROM importacoes WHERE id = ?", (resultado.importacao_id,)
            ).fetchone()

        assert imp["status"] == "concluido"
        assert imp["origem"] == "id_documentos"
        assert imp["arquivo_importado"] == "ID 24-04-2026.xlsx"
        assert imp["total_registros"] == 1

    def test_total_erros_inclui_inconsistencias(self, db, importer):
        db_path, contrato_id = db
        resultado = importer._importar_df(
            _df(_linha("INVALIDO", "Título")),
            "test.xlsx", contrato_id,
        )

        with get_connection(db_path) as conn:
            imp = conn.execute(
                "SELECT total_erros FROM importacoes WHERE id = ?",
                (resultado.importacao_id,),
            ).fetchone()

        assert imp["total_erros"] >= 1

    def test_importacao_limpa_tem_zero_erros(self, db, importer):
        db_path, contrato_id = db
        resultado = importer._importar_df(
            _df(_linha("DE-15.25.00.00-6A1-1001", "Desenho válido")),
            "test.xlsx", contrato_id,
        )

        with get_connection(db_path) as conn:
            imp = conn.execute(
                "SELECT total_erros FROM importacoes WHERE id = ?",
                (resultado.importacao_id,),
            ).fetchone()

        assert imp["total_erros"] == 0

    def test_contagens_novos_e_atualizados_no_log(self, db, importer):
        db_path, contrato_id = db
        df = _df(
            _linha("DE-15.25.00.00-6A1-1001"),
            _linha("RT-15.25.00.00-6A1-1001"),
        )
        resultado = importer._importar_df(df, "test.xlsx", contrato_id)

        with get_connection(db_path) as conn:
            imp = conn.execute(
                "SELECT total_novos, total_atualizados FROM importacoes WHERE id = ?",
                (resultado.importacao_id,),
            ).fetchone()

        assert imp["total_novos"] == 2
        assert imp["total_atualizados"] == 0
