"""
tests/test_engine/test_comparacao.py

Testes da comparação ID × Lista (core/engine/comparacao.py).

Execute com:
    pytest tests/ -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from core.engine.comparacao import comparar_id_lista, ResultadoComparacao
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
# Helpers
# ---------------------------------------------------------------------------

def _inserir_previsto(conn, cid, codigo, titulo="Título Previsto", trecho="25"):
    conn.execute(
        "INSERT INTO documentos_previstos (contrato_id, codigo, titulo, trecho, tipo) VALUES (?,?,?,?,?)",
        (cid, codigo, titulo, trecho, codigo.split("-")[0]),
    )


def _inserir_documento(conn, cid, codigo, titulo="Título Lista", trecho="25"):
    conn.execute(
        "INSERT OR IGNORE INTO documentos (contrato_id, codigo, titulo, trecho, tipo) VALUES (?,?,?,?,?)",
        (cid, codigo, titulo, trecho, codigo.split("-")[0]),
    )


# ---------------------------------------------------------------------------
# Banco vazio
# ---------------------------------------------------------------------------

class TestBancoVazio:

    def test_banco_vazio_retorna_dataframes_vazios(self, db):
        db_path, cid = db
        r = comparar_id_lista(cid, db_path)
        assert r.ausentes.empty
        assert r.extras.empty
        assert r.divergencias.empty
        assert r.encontrados.empty

    def test_totais_zerados(self, db):
        db_path, cid = db
        r = comparar_id_lista(cid, db_path)
        assert r.total_previstos == 0
        assert r.total_ausentes == 0
        assert r.total_extras == 0
        assert r.total_divergencias == 0
        assert r.total_encontrados == 0


# ---------------------------------------------------------------------------
# Ausentes na Lista
# ---------------------------------------------------------------------------

class TestAusentes:

    def test_previsto_sem_documento_e_ausente(self, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001")

        r = comparar_id_lista(cid, db_path)
        assert r.total_ausentes == 1
        assert r.ausentes.iloc[0]["codigo"] == "DE-15.25.00.00-6A1-1001"

    def test_previsto_com_documento_nao_e_ausente(self, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001")
            _inserir_documento(conn, cid, "DE-15.25.00.00-6A1-1001")

        r = comparar_id_lista(cid, db_path)
        assert r.total_ausentes == 0

    def test_multiplos_ausentes(self, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001")
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1002")
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1003")
            _inserir_documento(conn, cid, "DE-15.25.00.00-6A1-1001")  # só 1001 encontrado

        r = comparar_id_lista(cid, db_path)
        assert r.total_ausentes == 2
        codigos_ausentes = set(r.ausentes["codigo"])
        assert "DE-15.25.00.00-6A1-1002" in codigos_ausentes
        assert "DE-15.25.00.00-6A1-1003" in codigos_ausentes


# ---------------------------------------------------------------------------
# Extras na Lista
# ---------------------------------------------------------------------------

class TestExtras:

    def test_documento_sem_previsto_e_extra(self, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            _inserir_documento(conn, cid, "DE-15.25.00.00-6A1-9999")

        r = comparar_id_lista(cid, db_path)
        assert r.total_extras == 1
        assert r.extras.iloc[0]["codigo"] == "DE-15.25.00.00-6A1-9999"

    def test_documento_com_previsto_nao_e_extra(self, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001")
            _inserir_documento(conn, cid, "DE-15.25.00.00-6A1-1001")

        r = comparar_id_lista(cid, db_path)
        assert r.total_extras == 0

    def test_multiplos_extras(self, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001")
            _inserir_documento(conn, cid, "DE-15.25.00.00-6A1-1001")
            _inserir_documento(conn, cid, "DE-15.25.00.00-6A1-8001")  # extra
            _inserir_documento(conn, cid, "DE-15.25.00.00-6A1-8002")  # extra

        r = comparar_id_lista(cid, db_path)
        assert r.total_extras == 2
        codigos_extras = set(r.extras["codigo"])
        assert "DE-15.25.00.00-6A1-8001" in codigos_extras
        assert "DE-15.25.00.00-6A1-8002" in codigos_extras


# ---------------------------------------------------------------------------
# Divergências de título
# ---------------------------------------------------------------------------

class TestDivergencias:

    def test_titulos_iguais_sem_divergencia(self, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001", titulo="Fundações Bloco A")
            _inserir_documento(conn, cid, "DE-15.25.00.00-6A1-1001", titulo="Fundações Bloco A")

        r = comparar_id_lista(cid, db_path)
        assert r.total_divergencias == 0

    def test_titulos_diferentes_geram_divergencia(self, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001", titulo="Fundações Bloco A")
            _inserir_documento(conn, cid, "DE-15.25.00.00-6A1-1001", titulo="Fundações Bloco B")

        r = comparar_id_lista(cid, db_path)
        assert r.total_divergencias == 1
        div = r.divergencias.iloc[0]
        assert div["titulo_id"] == "Fundações Bloco A"
        assert div["titulo_lista"] == "Fundações Bloco B"

    def test_titulo_none_em_qualquer_lado_nao_e_divergencia(self, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001", titulo=None)
            _inserir_documento(conn, cid, "DE-15.25.00.00-6A1-1001", titulo="Qualquer Título")

        r = comparar_id_lista(cid, db_path)
        assert r.total_divergencias == 0

    def test_espacos_extras_ignorados_na_comparacao(self, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001", titulo="Fundações ")
            _inserir_documento(conn, cid, "DE-15.25.00.00-6A1-1001", titulo=" Fundações")

        r = comparar_id_lista(cid, db_path)
        # TRIM() aplicado na query — espaços não geram divergência
        assert r.total_divergencias == 0


# ---------------------------------------------------------------------------
# Encontrados e totais
# ---------------------------------------------------------------------------

class TestEncontrados:

    def test_total_previstos_e_ausentes_mais_encontrados(self, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001")  # encontrado
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1002")  # ausente
            _inserir_documento(conn, cid, "DE-15.25.00.00-6A1-1001")

        r = comparar_id_lista(cid, db_path)
        assert r.total_previstos == 2
        assert r.total_encontrados == 1
        assert r.total_ausentes == 1
        assert r.total_previstos == r.total_encontrados + r.total_ausentes

    def test_nome_trecho_presente_em_ausentes(self, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001", trecho="25")

        r = comparar_id_lista(cid, db_path)
        assert r.ausentes.iloc[0]["nome_trecho"] == "Ragueb Chohfi"

    def test_nome_trecho_presente_em_extras(self, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            _inserir_documento(conn, cid, "DE-15.23.17.84-6B3-1001", trecho="23")

        r = comparar_id_lista(cid, db_path)
        assert r.extras.iloc[0]["nome_trecho"] == "São Mateus"


# ---------------------------------------------------------------------------
# Cenário completo (todos os casos numa só fixture)
# ---------------------------------------------------------------------------

class TestCenarioCompleto:

    def test_cenario_misto(self, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001", titulo="Doc A")   # encontrado, título igual
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1002", titulo="Doc B")   # encontrado, título diferente
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1003")                   # ausente
            _inserir_documento(conn, cid, "DE-15.25.00.00-6A1-1001", titulo="Doc A")
            _inserir_documento(conn, cid, "DE-15.25.00.00-6A1-1002", titulo="Doc B2") # divergência
            _inserir_documento(conn, cid, "DE-15.25.00.00-6A1-9999")                  # extra

        r = comparar_id_lista(cid, db_path)
        assert r.total_previstos == 3
        assert r.total_encontrados == 2
        assert r.total_ausentes == 1
        assert r.total_extras == 1
        assert r.total_divergencias == 1
        assert r.ausentes.iloc[0]["codigo"] == "DE-15.25.00.00-6A1-1003"
        assert r.extras.iloc[0]["codigo"] == "DE-15.25.00.00-6A1-9999"
        assert r.divergencias.iloc[0]["codigo"] == "DE-15.25.00.00-6A1-1002"
