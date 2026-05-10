"""
tests/test_engine/test_emissao_inicial.py

Testes do motor de cálculo de EMISSÃO INICIAL.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from core.engine.emissao_inicial import recalcular_emissao_inicial
from db.connection import get_connection

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scripts"))
from init_db import init_db


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path, verbose=False)
    with get_connection(db_path) as conn:
        conn.execute("INSERT INTO contratos (nome) VALUES ('Teste')")
        cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO documentos (contrato_id, codigo, tipo) VALUES (?,?,?)",
            (cid, "DE-15.25.00.00-6A1-1001", "DE"),
        )
        did = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return db_path, did


def _inserir_revisao(conn, doc_id, label, versao, data_emissao, situacao=None):
    conn.execute(
        """
        INSERT INTO revisoes
            (documento_id, revisao, versao, label_revisao,
             data_emissao, situacao, ultima_revisao, origem)
        VALUES (?, ?, ?, ?, ?, ?, 0, 'teste')
        """,
        (doc_id, int(label) if label.isdigit() else None, versao, label, data_emissao, situacao),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _labels(db_path, doc_id):
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT label_revisao, versao, emissao_inicial
            FROM revisoes
            WHERE documento_id = ?
            ORDER BY
                CASE WHEN data_emissao IS NULL THEN 1 ELSE 0 END,
                data_emissao ASC, revisao ASC, versao ASC
            """,
            (doc_id,),
        ).fetchall()
    return [r["emissao_inicial"] for r in rows]


# ---------------------------------------------------------------------------
# Revisão única
# ---------------------------------------------------------------------------

class TestRevisaoUnica:

    def test_revisao_unica_emissao_inicial(self, db):
        db_path, did = db
        with get_connection(db_path) as conn:
            _inserir_revisao(conn, did, "0", 1, "2024-01-10")
            recalcular_emissao_inicial(conn, did)
        assert _labels(db_path, did) == ["EMISSÃO INICIAL"]

    def test_revisao_unica_aprovada_ainda_eh_emissao_inicial(self, db):
        """Uma única revisão é sempre EMISSÃO INICIAL, mesmo que aprovada."""
        db_path, did = db
        with get_connection(db_path) as conn:
            _inserir_revisao(conn, did, "0", 1, "2024-01-10", situacao="APROVADO")
            recalcular_emissao_inicial(conn, did)
        assert _labels(db_path, did) == ["EMISSÃO INICIAL"]


# ---------------------------------------------------------------------------
# Duas revisões
# ---------------------------------------------------------------------------

class TestDuasRevisoes:

    def test_dois_nao_aprovado_revisao_1(self, db):
        db_path, did = db
        with get_connection(db_path) as conn:
            _inserir_revisao(conn, did, "0", 1, "2024-01-10")
            _inserir_revisao(conn, did, "1", 1, "2024-03-10", situacao="NÃO APROVADO")
            recalcular_emissao_inicial(conn, did)
        assert _labels(db_path, did) == ["EMISSÃO INICIAL", "REVISÃO 1"]

    def test_dois_segundo_aprovado_revisao_final(self, db):
        db_path, did = db
        with get_connection(db_path) as conn:
            _inserir_revisao(conn, did, "0", 1, "2024-01-10")
            _inserir_revisao(conn, did, "1", 1, "2024-03-10", situacao="APROVADO")
            recalcular_emissao_inicial(conn, did)
        assert _labels(db_path, did) == ["EMISSÃO INICIAL", "REVISÃO FINAL"]

    def test_para_aprovacao_ativa_revisao_final(self, db):
        db_path, did = db
        with get_connection(db_path) as conn:
            _inserir_revisao(conn, did, "0", 1, "2024-01-10")
            _inserir_revisao(conn, did, "1", 1, "2024-03-10", situacao="PARA APROVAÇÃO")
            recalcular_emissao_inicial(conn, did)
        assert _labels(db_path, did) == ["EMISSÃO INICIAL", "REVISÃO FINAL"]

    def test_em_coleta_de_assinaturas_ativa_revisao_final(self, db):
        db_path, did = db
        with get_connection(db_path) as conn:
            _inserir_revisao(conn, did, "0", 1, "2024-01-10")
            _inserir_revisao(conn, did, "1", 1, "2024-03-10", situacao="EM COLETA DE ASSINATURAS")
            recalcular_emissao_inicial(conn, did)
        assert _labels(db_path, did) == ["EMISSÃO INICIAL", "REVISÃO FINAL"]


# ---------------------------------------------------------------------------
# Três ou mais revisões
# ---------------------------------------------------------------------------

class TestTresRevisoes:

    def test_tres_ultima_nao_aprovada(self, db):
        db_path, did = db
        with get_connection(db_path) as conn:
            _inserir_revisao(conn, did, "0", 1, "2024-01-10")
            _inserir_revisao(conn, did, "1", 1, "2024-03-10", situacao="NÃO APROVADO")
            _inserir_revisao(conn, did, "2", 1, "2024-06-10", situacao="NÃO APROVADO")
            recalcular_emissao_inicial(conn, did)
        assert _labels(db_path, did) == ["EMISSÃO INICIAL", "REVISÃO 1", "REVISÃO 2"]

    def test_tres_ultima_aprovada(self, db):
        db_path, did = db
        with get_connection(db_path) as conn:
            _inserir_revisao(conn, did, "0", 1, "2024-01-10")
            _inserir_revisao(conn, did, "1", 1, "2024-03-10", situacao="NÃO APROVADO")
            _inserir_revisao(conn, did, "2", 1, "2024-06-10", situacao="APROVADO")
            recalcular_emissao_inicial(conn, did)
        assert _labels(db_path, did) == ["EMISSÃO INICIAL", "REVISÃO 1", "REVISÃO FINAL"]

    def test_revisao_do_meio_aprovada_nao_vira_final(self, db):
        """Aprovação em revisão intermediária não dispara REVISÃO FINAL — só a última."""
        db_path, did = db
        with get_connection(db_path) as conn:
            _inserir_revisao(conn, did, "0", 1, "2024-01-10")
            _inserir_revisao(conn, did, "1", 1, "2024-03-10", situacao="APROVADO")
            _inserir_revisao(conn, did, "2", 1, "2024-06-10", situacao="NÃO APROVADO")
            recalcular_emissao_inicial(conn, did)
        assert _labels(db_path, did) == ["EMISSÃO INICIAL", "REVISÃO 1", "REVISÃO 2"]

    def test_quatro_revisoes_sequencia(self, db):
        db_path, did = db
        with get_connection(db_path) as conn:
            _inserir_revisao(conn, did, "0", 1, "2024-01-10")
            _inserir_revisao(conn, did, "1", 1, "2024-03-10")
            _inserir_revisao(conn, did, "2", 1, "2024-06-10")
            _inserir_revisao(conn, did, "3", 1, "2024-09-10", situacao="APROVADO")
            recalcular_emissao_inicial(conn, did)
        assert _labels(db_path, did) == [
            "EMISSÃO INICIAL", "REVISÃO 1", "REVISÃO 2", "REVISÃO FINAL"
        ]


# ---------------------------------------------------------------------------
# Ordenação por data_emissao (não por label/versão)
# ---------------------------------------------------------------------------

class TestOrdenacaoPorData:

    def test_data_emissao_mais_antiga_e_emissao_inicial(self, db):
        """Inserção fora de ordem: revisão com data mais antiga = EMISSÃO INICIAL."""
        db_path, did = db
        with get_connection(db_path) as conn:
            # Insere Rev 1 antes de Rev 0 no banco, mas Rev 0 tem data mais antiga
            _inserir_revisao(conn, did, "1", 1, "2024-06-10")
            _inserir_revisao(conn, did, "0", 1, "2024-01-10")
            recalcular_emissao_inicial(conn, did)
        labels = _labels(db_path, did)
        assert labels[0] == "EMISSÃO INICIAL"
        assert labels[1] == "REVISÃO 1"

    def test_sem_data_emissao_fica_por_ultimo(self, db):
        """Revisão sem data de emissão vai para o final da ordenação."""
        db_path, did = db
        with get_connection(db_path) as conn:
            _inserir_revisao(conn, did, "0", 1, "2024-01-10")
            _inserir_revisao(conn, did, "1", 1, None)   # sem data
            recalcular_emissao_inicial(conn, did)
        labels = _labels(db_path, did)
        assert labels[0] == "EMISSÃO INICIAL"
        assert labels[1] == "REVISÃO 1"

    def test_recalculo_idempotente(self, db):
        """Chamar recalcular duas vezes produz o mesmo resultado."""
        db_path, did = db
        with get_connection(db_path) as conn:
            _inserir_revisao(conn, did, "0", 1, "2024-01-10")
            _inserir_revisao(conn, did, "1", 1, "2024-06-10", situacao="APROVADO")
            recalcular_emissao_inicial(conn, did)
            recalcular_emissao_inicial(conn, did)
        assert _labels(db_path, did) == ["EMISSÃO INICIAL", "REVISÃO FINAL"]


# ---------------------------------------------------------------------------
# Migração de schema — banco antigo sem a coluna emissao_inicial
# ---------------------------------------------------------------------------

class TestMigracaoSchema:

    def test_coluna_emissao_inicial_adicionada_em_banco_antigo(self, tmp_path):
        """init_db migra banco que não tem emissao_inicial em revisoes."""
        import sqlite3
        db_path = str(tmp_path / "antigo.db")

        # Cria banco mínimo sem coluna emissao_inicial
        with sqlite3.connect(db_path) as conn:
            conn.executescript("""
                CREATE TABLE contratos (id INTEGER PRIMARY KEY, nome TEXT);
                CREATE TABLE documentos (
                    id INTEGER PRIMARY KEY, contrato_id INTEGER, codigo TEXT,
                    tipo TEXT, titulo TEXT, disciplina TEXT, modalidade TEXT,
                    trecho TEXT, nome_trecho TEXT, responsavel TEXT,
                    origem TEXT DEFAULT 'importacao_lista',
                    criado_em TEXT DEFAULT (datetime('now')),
                    atualizado_em TEXT DEFAULT (datetime('now')),
                    UNIQUE(contrato_id, codigo)
                );
                CREATE TABLE revisoes (
                    id INTEGER PRIMARY KEY, documento_id INTEGER,
                    revisao INTEGER, versao INTEGER, label_revisao TEXT,
                    data_emissao TEXT, situacao TEXT,
                    ultima_revisao INTEGER DEFAULT 0,
                    criado_em TEXT DEFAULT (datetime('now')),
                    UNIQUE(documento_id, revisao, versao)
                );
                CREATE TABLE arquivos (
                    id INTEGER PRIMARY KEY, documento_id INTEGER,
                    nome_arquivo TEXT, extensao TEXT,
                    UNIQUE(documento_id, nome_arquivo)
                );
            """)

        init_db(db_path, verbose=False)

        with sqlite3.connect(db_path) as conn:
            colunas_rev = {row[1] for row in conn.execute("PRAGMA table_info(revisoes)")}
            colunas_doc = {row[1] for row in conn.execute("PRAGMA table_info(documentos)")}
            colunas_arq = {row[1] for row in conn.execute("PRAGMA table_info(arquivos)")}
            tabelas = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

        assert "emissao_inicial" in colunas_rev
        assert "data_circular"   in colunas_rev
        assert "fase"            in colunas_doc
        assert "objeto"          in colunas_arq
        assert "grds"            in tabelas
