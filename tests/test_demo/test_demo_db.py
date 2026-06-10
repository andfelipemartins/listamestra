"""
tests/test_demo/test_demo_db.py

Testes do banco demo fictício e da seleção de banco por modo (SCLME_DB_MODE).
"""

import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scripts"))

from create_demo_db import criar_banco_demo
import db.connection as conn_mod


# ---------------------------------------------------------------------------
# Builder do banco demo
# ---------------------------------------------------------------------------

@pytest.fixture
def demo_db(tmp_path):
    path = str(tmp_path / "demo" / "sclme_demo.db")
    criar_banco_demo(path)
    return path


def _conn(path):
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    return c


class TestBuilder:
    def test_cria_do_zero(self, tmp_path):
        path = str(tmp_path / "demo" / "sclme_demo.db")
        assert not os.path.exists(path)
        criar_banco_demo(path)
        assert os.path.exists(path)

    def test_recria_idempotente(self, tmp_path):
        path = str(tmp_path / "demo" / "sclme_demo.db")
        criar_banco_demo(path)
        criar_banco_demo(path)  # não deve falhar (remove e recria)
        assert _conn(path).execute("SELECT COUNT(*) FROM contratos").fetchone()[0] == 1

    def test_contem_contrato_demo(self, demo_db):
        row = _conn(demo_db).execute("SELECT nome, cliente FROM contratos").fetchone()
        assert row["nome"] == "Demo Linha 15"
        assert row["cliente"] == "Cliente Demonstração"

    def test_minimos_de_dados(self, demo_db):
        c = _conn(demo_db)
        def n(q): return c.execute(q).fetchone()[0]
        assert n("SELECT COUNT(*) FROM documentos_previstos") >= 20
        assert n("SELECT COUNT(*) FROM documentos") >= 15
        assert n("SELECT COUNT(*) FROM revisoes") >= 15
        assert n("SELECT COUNT(*) FROM grd_remessas") >= 3

    def test_tres_trechos(self, demo_db):
        trechos = {r[0] for r in _conn(demo_db).execute("SELECT DISTINCT trecho FROM documentos")}
        assert {"19", "23", "25"} <= trechos

    def test_grds_com_status_variados(self, demo_db):
        status = {r[0] for r in _conn(demo_db).execute("SELECT status FROM grd_remessas")}
        assert {"emitida", "enviada", "recebida", "anulada"} <= status

    def test_grd_recebida_tem_dados_de_recebimento(self, demo_db):
        row = _conn(demo_db).execute(
            "SELECT recebido_por, recebido_cargo, recebido_em, declaracao_recebimento "
            "FROM grd_remessas WHERE status='recebida'"
        ).fetchone()
        assert row["recebido_por"] and row["recebido_cargo"]
        assert row["recebido_em"] and row["declaracao_recebimento"]

    def test_grd_anulada_tem_motivo(self, demo_db):
        row = _conn(demo_db).execute(
            "SELECT motivo_anulacao, anulada_em FROM grd_remessas WHERE status='anulada'"
        ).fetchone()
        assert row["motivo_anulacao"] and row["anulada_em"]

    def test_itens_tem_snapshot(self, demo_db):
        row = _conn(demo_db).execute(
            "SELECT codigo_snapshot, qtd_a1 FROM grd_itens LIMIT 1"
        ).fetchone()
        assert row["codigo_snapshot"]

    def test_sem_dados_reais_obvios(self, demo_db):
        """Sanidade: títulos são claramente de demonstração."""
        titulos = [r[0] for r in _conn(demo_db).execute(
            "SELECT titulo FROM documentos WHERE titulo IS NOT NULL"
        )]
        assert titulos and all("DEMO" in (t or "").upper() for t in titulos)


# ---------------------------------------------------------------------------
# Seleção de banco por modo (SCLME_DB_MODE)
# ---------------------------------------------------------------------------

class TestModoDeBanco:
    def test_default_usa_operacional(self, monkeypatch):
        monkeypatch.delenv("SCLME_DB_MODE", raising=False)
        assert conn_mod.modo_demo() is False
        assert conn_mod.resolver_db_path() == conn_mod.DB_PATH_OPERACIONAL
        assert conn_mod.DB_PATH_OPERACIONAL.endswith("sclme.db")

    def test_modo_demo_usa_demo(self, monkeypatch):
        monkeypatch.setenv("SCLME_DB_MODE", "demo")
        assert conn_mod.modo_demo() is True
        assert conn_mod.resolver_db_path() == conn_mod.DB_PATH_DEMO
        assert conn_mod.DB_PATH_DEMO.replace("\\", "/").endswith("data/demo/sclme_demo.db")

    def test_modo_demo_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("SCLME_DB_MODE", "DEMO")
        assert conn_mod.modo_demo() is True

    def test_valor_desconhecido_usa_operacional(self, monkeypatch):
        monkeypatch.setenv("SCLME_DB_MODE", "produção")
        assert conn_mod.resolver_db_path() == conn_mod.DB_PATH_OPERACIONAL

    def test_get_connection_explicito_ignora_modo(self, monkeypatch, tmp_path):
        """db_path explícito tem prioridade sobre o modo."""
        monkeypatch.setenv("SCLME_DB_MODE", "demo")
        alvo = str(tmp_path / "explicito.db")
        with conn_mod.get_connection(alvo) as c:
            c.execute("CREATE TABLE t (x)")
        assert os.path.exists(alvo)
