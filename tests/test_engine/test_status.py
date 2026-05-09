"""
tests/test_engine/test_status.py

Testes da classificação de status documental (core/engine/status.py).

Execute com:
    pytest tests/ -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from core.engine.status import classificar_status, carregar_progresso
from db.connection import get_connection

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scripts"))
from init_db import init_db


# ---------------------------------------------------------------------------
# Fixture de banco
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path, verbose=False)
    with get_connection(db_path) as conn:
        conn.execute("INSERT INTO contratos (nome) VALUES ('Contrato Teste')")
        cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return db_path, cid


# ---------------------------------------------------------------------------
# Testes de classificar_status (função pura — sem banco)
# ---------------------------------------------------------------------------

class TestClassificarStatus:

    def test_aprovado(self):
        assert classificar_status("APROVADO", "2024-10-07") == "Aprovado"

    def test_aprovado_caixa_baixa(self):
        assert classificar_status("aprovado", "2024-10-07") == "Aprovado"

    def test_nao_aprovado_e_em_revisao(self):
        assert classificar_status("NÃO APROVADO", "2024-10-07") == "Em Revisão"

    def test_nao_aprovado_sem_data_emissao(self):
        # Situação estranha mas possível; NÃO APROVADO tem precedência
        assert classificar_status("NÃO APROVADO", None) == "Em Revisão"

    def test_com_data_emissao_sem_situacao(self):
        assert classificar_status(None, "2024-10-07") == "Em Análise"

    def test_com_data_emissao_situacao_vazia(self):
        assert classificar_status("", "2024-10-07") == "Em Análise"

    def test_sem_nada_e_em_elaboracao(self):
        assert classificar_status(None, None) == "Em Elaboração"

    def test_situacao_vazia_sem_data_e_em_elaboracao(self):
        assert classificar_status("", None) == "Em Elaboração"

    def test_aprovado_nao_confunde_com_nao_aprovado(self):
        # "NÃO APROVADO" contém "APROVADO" — a ordem de verificação importa
        assert classificar_status("NÃO APROVADO", "2024-10-07") == "Em Revisão"
        assert classificar_status("APROVADO", "2024-10-07") == "Aprovado"

    @pytest.mark.parametrize("situacao,data_emissao,esperado", [
        ("APROVADO",      "2024-10-07", "Aprovado"),
        ("NÃO APROVADO",  "2024-10-07", "Em Revisão"),
        (None,            "2024-10-07", "Em Análise"),
        ("",              "2024-10-07", "Em Análise"),
        (None,            None,         "Em Elaboração"),
        ("",              None,         "Em Elaboração"),
    ])
    def test_matriz_de_status(self, situacao, data_emissao, esperado):
        assert classificar_status(situacao, data_emissao) == esperado


# ---------------------------------------------------------------------------
# Testes de carregar_progresso (integração com banco)
# ---------------------------------------------------------------------------

class TestCarregarProgresso:

    def _inserir_previsto(self, conn, contrato_id, codigo, trecho="25"):
        conn.execute(
            "INSERT INTO documentos_previstos (contrato_id, codigo, trecho, tipo) VALUES (?, ?, ?, ?)",
            (contrato_id, codigo, trecho, codigo.split("-")[0]),
        )

    def _inserir_documento_revisao(self, conn, contrato_id, codigo,
                                   situacao=None, data_emissao=None):
        conn.execute(
            "INSERT OR IGNORE INTO documentos (contrato_id, codigo, tipo) VALUES (?, ?, ?)",
            (contrato_id, codigo, codigo.split("-")[0]),
        )
        doc_id = conn.execute(
            "SELECT id FROM documentos WHERE contrato_id=? AND codigo=?",
            (contrato_id, codigo),
        ).fetchone()[0]
        conn.execute(
            """INSERT INTO revisoes
               (documento_id, revisao, versao, situacao, data_emissao, ultima_revisao)
               VALUES (?, 1, 1, ?, ?, 1)""",
            (doc_id, situacao, data_emissao),
        )

    def test_previsto_sem_lista_e_em_elaboracao(self, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            self._inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001")

        df = carregar_progresso(cid, db_path)
        assert len(df) == 1
        assert df.iloc[0]["status"] == "Em Elaboração"

    def test_previsto_com_revisao_aprovada(self, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            self._inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001")
            self._inserir_documento_revisao(conn, cid, "DE-15.25.00.00-6A1-1001",
                                            situacao="APROVADO", data_emissao="2024-10-07")

        df = carregar_progresso(cid, db_path)
        assert df.iloc[0]["status"] == "Aprovado"

    def test_previsto_nao_aprovado_e_em_revisao(self, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            self._inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001")
            self._inserir_documento_revisao(conn, cid, "DE-15.25.00.00-6A1-1001",
                                            situacao="NÃO APROVADO", data_emissao="2024-10-07")

        df = carregar_progresso(cid, db_path)
        assert df.iloc[0]["status"] == "Em Revisão"

    def test_previsto_emitido_sem_situacao_e_em_analise(self, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            self._inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001")
            self._inserir_documento_revisao(conn, cid, "DE-15.25.00.00-6A1-1001",
                                            data_emissao="2024-10-07")

        df = carregar_progresso(cid, db_path)
        assert df.iloc[0]["status"] == "Em Análise"

    def test_trecho_mapeado_para_nome(self, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            self._inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001", trecho="25")
            self._inserir_previsto(conn, cid, "DE-15.23.17.84-6B3-1001", trecho="23")

        df = carregar_progresso(cid, db_path)
        nomes = dict(zip(df["trecho"], df["nome_trecho"]))
        assert nomes["25"] == "Ragueb Chohfi"
        assert nomes["23"] == "São Mateus"

    def test_banco_sem_previstos_retorna_dataframe_vazio(self, db):
        db_path, cid = db
        df = carregar_progresso(cid, db_path)
        assert df.empty

    def test_multiplos_documentos_status_corretos(self, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            self._inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001")
            self._inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1002")
            self._inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1003")
            self._inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1004")

            self._inserir_documento_revisao(conn, cid, "DE-15.25.00.00-6A1-1001",
                                            situacao="APROVADO", data_emissao="2024-10-07")
            self._inserir_documento_revisao(conn, cid, "DE-15.25.00.00-6A1-1002",
                                            situacao="NÃO APROVADO", data_emissao="2024-10-07")
            self._inserir_documento_revisao(conn, cid, "DE-15.25.00.00-6A1-1003",
                                            data_emissao="2024-10-07")
            # 1004 sem entrada na Lista → Em Elaboração

        df = carregar_progresso(cid, db_path)
        status_por_codigo = dict(zip(df["codigo"], df["status"]))

        assert status_por_codigo["DE-15.25.00.00-6A1-1001"] == "Aprovado"
        assert status_por_codigo["DE-15.25.00.00-6A1-1002"] == "Em Revisão"
        assert status_por_codigo["DE-15.25.00.00-6A1-1003"] == "Em Análise"
        assert status_por_codigo["DE-15.25.00.00-6A1-1004"] == "Em Elaboração"
