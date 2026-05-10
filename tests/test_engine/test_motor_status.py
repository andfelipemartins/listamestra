"""
tests/test_engine/test_motor_status.py

Testes da função carregar_alertas() — Motor de Status (Marco 9).
"""

import os
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from core.engine.status import carregar_alertas
from db.connection import get_connection

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scripts"))
from init_db import init_db


# ---------------------------------------------------------------------------
# Fixture e helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path, verbose=False)
    with get_connection(db_path) as conn:
        conn.execute("INSERT INTO contratos (nome) VALUES ('Contrato Teste')")
        cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return db_path, cid


def _data_passada(dias: int) -> str:
    """Retorna uma data ISO exatamente `dias` dias no passado."""
    return (date.today() - timedelta(days=dias)).isoformat()


def _inserir_previsto(conn, contrato_id, codigo):
    conn.execute(
        "INSERT INTO documentos_previstos (contrato_id, codigo, tipo, trecho) VALUES (?, ?, ?, '25')",
        (contrato_id, codigo, codigo.split("-")[0]),
    )


def _inserir_doc_com_revisao(conn, contrato_id, codigo,
                              situacao=None, data_emissao=None,
                              titulo="Título Teste"):
    conn.execute(
        "INSERT OR IGNORE INTO documentos (contrato_id, codigo, tipo, titulo) VALUES (?, ?, ?, ?)",
        (contrato_id, codigo, codigo.split("-")[0], titulo),
    )
    doc_id = conn.execute(
        "SELECT id FROM documentos WHERE contrato_id = ? AND codigo = ?",
        (contrato_id, codigo),
    ).fetchone()[0]
    conn.execute(
        """
        INSERT INTO revisoes
            (documento_id, revisao, versao, situacao, data_emissao, ultima_revisao)
        VALUES (?, 1, 1, ?, ?, 1)
        """,
        (doc_id, situacao, data_emissao),
    )
    return doc_id


# ---------------------------------------------------------------------------
# Sem alertas
# ---------------------------------------------------------------------------

class TestSemAlertas:

    def test_sem_documentos_retorna_lista_vazia(self, db):
        db_path, cid = db
        alertas = carregar_alertas(cid, db_path=db_path)
        assert alertas == []

    def test_previsto_sem_revisao_mas_nao_cadastrado_no_id_nao_alerta(self, db):
        """Documento na tabela documentos mas sem revisão NÃO gera sem_inicio se não for previsto."""
        db_path, cid = db
        with get_connection(db_path) as conn:
            _inserir_doc_com_revisao(conn, cid, "DE-15.25.00.00-6A1-1001",
                                     data_emissao=_data_passada(60))
        # Sem documentos_previstos, não deve gerar nenhum alerta
        alertas = carregar_alertas(cid, db_path=db_path)
        assert alertas == []

    def test_aprovado_antigo_nao_gera_alerta(self, db):
        """Documento aprovado há muito tempo não deve gerar alerta de análise prolongada."""
        db_path, cid = db
        with get_connection(db_path) as conn:
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001")
            _inserir_doc_com_revisao(conn, cid, "DE-15.25.00.00-6A1-1001",
                                     situacao="APROVADO", data_emissao=_data_passada(365))
        alertas = carregar_alertas(cid, db_path=db_path)
        assert alertas == []

    def test_em_analise_dentro_do_prazo_nao_alerta(self, db):
        """Documento Em Análise dentro do threshold não deve alertar."""
        db_path, cid = db
        with get_connection(db_path) as conn:
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001")
            _inserir_doc_com_revisao(conn, cid, "DE-15.25.00.00-6A1-1001",
                                     data_emissao=_data_passada(10))
        alertas = carregar_alertas(cid, dias_analise=30, db_path=db_path)
        assert alertas == []

    def test_claramente_abaixo_do_limite_nao_alerta(self, db):
        """Documento emitido há 29 dias com threshold de 30 — nunca deve alertar."""
        db_path, cid = db
        with get_connection(db_path) as conn:
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001")
            _inserir_doc_com_revisao(conn, cid, "DE-15.25.00.00-6A1-1001",
                                     data_emissao=_data_passada(29))
        alertas = carregar_alertas(cid, dias_analise=30, db_path=db_path)
        assert alertas == []


# ---------------------------------------------------------------------------
# Alertas de análise prolongada
# ---------------------------------------------------------------------------

class TestAnaliseProlongada:

    def test_em_analise_alem_do_prazo_gera_alerta(self, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001")
            _inserir_doc_com_revisao(conn, cid, "DE-15.25.00.00-6A1-1001",
                                     data_emissao=_data_passada(45))
        alertas = carregar_alertas(cid, dias_analise=30, db_path=db_path)
        assert len(alertas) == 1
        assert alertas[0]["tipo"] == "analise_prolongada"
        assert alertas[0]["codigo"] == "DE-15.25.00.00-6A1-1001"
        assert alertas[0]["dias"] > 30

    def test_em_revisao_alem_do_prazo_gera_alerta(self, db):
        """Documento Em Revisão (NÃO APROVADO) também gera alerta de análise prolongada."""
        db_path, cid = db
        with get_connection(db_path) as conn:
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001")
            _inserir_doc_com_revisao(conn, cid, "DE-15.25.00.00-6A1-1001",
                                     situacao="NÃO APROVADO", data_emissao=_data_passada(60))
        alertas = carregar_alertas(cid, dias_analise=30, db_path=db_path)
        assert len(alertas) == 1
        assert alertas[0]["tipo"] == "analise_prolongada"
        assert alertas[0]["mensagem"].startswith("Em em revisão")

    def test_alerta_contem_campos_obrigatorios(self, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001")
            _inserir_doc_com_revisao(conn, cid, "DE-15.25.00.00-6A1-1001",
                                     data_emissao=_data_passada(50),
                                     titulo="Memorial de Cálculo Estrutural")
        alertas = carregar_alertas(cid, dias_analise=30, db_path=db_path)
        a = alertas[0]
        assert "tipo" in a
        assert "codigo" in a
        assert "titulo" in a
        assert "dias" in a
        assert "data_referencia" in a
        assert "mensagem" in a

    def test_threshold_customizado(self, db):
        """Threshold de 7 dias deve alertar documento emitido há 10 dias."""
        db_path, cid = db
        with get_connection(db_path) as conn:
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001")
            _inserir_doc_com_revisao(conn, cid, "DE-15.25.00.00-6A1-1001",
                                     data_emissao=_data_passada(10))
        alertas = carregar_alertas(cid, dias_analise=7, db_path=db_path)
        assert len(alertas) == 1
        assert alertas[0]["tipo"] == "analise_prolongada"


# ---------------------------------------------------------------------------
# Alertas de sem_inicio
# ---------------------------------------------------------------------------

class TestSemInicio:

    def test_previsto_sem_revisao_gera_alerta_sem_inicio(self, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001")
        alertas = carregar_alertas(cid, db_path=db_path)
        assert len(alertas) == 1
        assert alertas[0]["tipo"] == "sem_inicio"
        assert alertas[0]["codigo"] == "DE-15.25.00.00-6A1-1001"

    def test_sem_inicio_sem_data_nem_dias(self, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001")
        alertas = carregar_alertas(cid, db_path=db_path)
        a = alertas[0]
        assert a["dias"] is None
        assert a["data_referencia"] is None

    def test_previsto_com_revisao_nao_gera_sem_inicio(self, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001")
            _inserir_doc_com_revisao(conn, cid, "DE-15.25.00.00-6A1-1001")
        alertas = carregar_alertas(cid, db_path=db_path)
        tipos = [a["tipo"] for a in alertas]
        assert "sem_inicio" not in tipos


# ---------------------------------------------------------------------------
# Múltiplos alertas e tipos mistos
# ---------------------------------------------------------------------------

class TestMultiplosAlertas:

    def test_dois_tipos_de_alerta_juntos(self, db):
        """Um documento em análise prolongada + um previsto sem revisão."""
        db_path, cid = db
        with get_connection(db_path) as conn:
            # Analise prolongada
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001")
            _inserir_doc_com_revisao(conn, cid, "DE-15.25.00.00-6A1-1001",
                                     data_emissao=_data_passada(60))
            # Sem inicio
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1002")

        alertas = carregar_alertas(cid, dias_analise=30, db_path=db_path)
        tipos = {a["tipo"] for a in alertas}
        assert "analise_prolongada" in tipos
        assert "sem_inicio" in tipos
        assert len(alertas) == 2

    def test_aprovado_e_em_analise_no_prazo_nao_geram_alertas(self, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1001")
            _inserir_doc_com_revisao(conn, cid, "DE-15.25.00.00-6A1-1001",
                                     situacao="APROVADO", data_emissao=_data_passada(200))
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1002")
            _inserir_doc_com_revisao(conn, cid, "DE-15.25.00.00-6A1-1002",
                                     data_emissao=_data_passada(5))

        alertas = carregar_alertas(cid, dias_analise=30, db_path=db_path)
        assert alertas == []

    def test_contagem_precisa_com_varios_documentos(self, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            for i in range(1, 4):
                codigo = f"DE-15.25.00.00-6A1-100{i}"
                _inserir_previsto(conn, cid, codigo)
                _inserir_doc_com_revisao(conn, cid, codigo,
                                         data_emissao=_data_passada(50))
            # Um sem revisão
            _inserir_previsto(conn, cid, "DE-15.25.00.00-6A1-1004")

        alertas = carregar_alertas(cid, dias_analise=30, db_path=db_path)
        analise = [a for a in alertas if a["tipo"] == "analise_prolongada"]
        sem_inicio = [a for a in alertas if a["tipo"] == "sem_inicio"]
        assert len(analise) == 3
        assert len(sem_inicio) == 1
