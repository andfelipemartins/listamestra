"""
tests/test_importers/test_cadastro_importer.py

Testes de salvar_documento_revisao (Cadastro Manual).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scripts"))

from init_db import init_db
from core.importers.cadastro_importer import salvar_documento_revisao
from db.connection import get_connection


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    init_db(path, verbose=False)
    return path


@pytest.fixture
def contrato_id(db_path):
    with get_connection(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO contratos (nome, cliente) VALUES (?, ?)",
            ("Contrato Teste", "Cliente Teste"),
        )
        return cur.lastrowid


def _doc_fields(titulo="Meu Documento"):
    return {
        "titulo":      titulo,
        "responsavel": "Fulano",
        "modalidade":  "CIVIL",
        "disciplina":  "E1",
        "fase":        "EXECUTIVO",
    }


def _rev_fields(label="0", versao=1, data_emissao=None):
    return {
        "label_revisao":   label,
        "versao":          versao,
        "data_elaboracao": None,
        "data_emissao":    data_emissao,
        "data_analise":    None,
        "situacao":        "APROVADO",
        "situacao_real":   None,
        "analise_interna": None,
        "data_circular":   None,
        "num_circular":    None,
    }


_CODIGO = "DE-15.25.00.00-6A1-1001"
_CODIGO2 = "DE-15.25.00.00-6A1-1002"


# ---------------------------------------------------------------------------
# Cadastro unitário
# ---------------------------------------------------------------------------

class TestCadastroUnitario:

    def test_salva_documento_novo(self, db_path, contrato_id):
        msg = salvar_documento_revisao(
            contrato_id, _CODIGO, _doc_fields(), _rev_fields(), [], db_path=db_path
        )
        assert "sucesso" in msg.lower()

    def test_documento_criado_no_banco(self, db_path, contrato_id):
        salvar_documento_revisao(
            contrato_id, _CODIGO, _doc_fields(), _rev_fields(), [], db_path=db_path
        )
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT * FROM documentos WHERE codigo = ? AND contrato_id = ?",
                (_CODIGO, contrato_id),
            ).fetchone()
        assert row is not None
        assert row["titulo"] == "Meu Documento"
        assert row["origem"] == "cadastro_manual"

    def test_revisao_criada_no_banco(self, db_path, contrato_id):
        salvar_documento_revisao(
            contrato_id, _CODIGO, _doc_fields(), _rev_fields(), [], db_path=db_path
        )
        with get_connection(db_path) as conn:
            doc = conn.execute(
                "SELECT id FROM documentos WHERE codigo = ?", (_CODIGO,)
            ).fetchone()
            rev = conn.execute(
                "SELECT * FROM revisoes WHERE documento_id = ?", (doc["id"],)
            ).fetchone()
        assert rev is not None
        assert rev["label_revisao"] == "0"
        assert rev["versao"] == 1
        assert rev["origem"] == "cadastro_manual"

    def test_msg_indica_documento_criado(self, db_path, contrato_id):
        msg = salvar_documento_revisao(
            contrato_id, _CODIGO, _doc_fields(), _rev_fields(), [], db_path=db_path
        )
        assert "criado" in msg.lower()

    def test_msg_indica_revisao_existente_ao_adicionar_segunda(self, db_path, contrato_id):
        salvar_documento_revisao(
            contrato_id, _CODIGO, _doc_fields(), _rev_fields("0", 1), [], db_path=db_path
        )
        msg = salvar_documento_revisao(
            contrato_id, _CODIGO, _doc_fields(), _rev_fields("1", 1), [], db_path=db_path
        )
        assert "sucesso" in msg.lower()

    def test_ultima_revisao_marcada_corretamente(self, db_path, contrato_id):
        salvar_documento_revisao(
            contrato_id, _CODIGO, _doc_fields(), _rev_fields("0", 1, "2024-01-10"), [], db_path=db_path
        )
        salvar_documento_revisao(
            contrato_id, _CODIGO, _doc_fields(), _rev_fields("1", 1, "2024-06-15"), [], db_path=db_path
        )
        with get_connection(db_path) as conn:
            doc = conn.execute("SELECT id FROM documentos WHERE codigo = ?", (_CODIGO,)).fetchone()
            ultimas = conn.execute(
                "SELECT label_revisao FROM revisoes WHERE documento_id = ? AND ultima_revisao = 1",
                (doc["id"],),
            ).fetchall()
        assert len(ultimas) == 1
        assert ultimas[0]["label_revisao"] == "1"


# ---------------------------------------------------------------------------
# Proteção contra duplicata
# ---------------------------------------------------------------------------

class TestNaoDuplica:

    def test_revisao_duplicada_retorna_aviso(self, db_path, contrato_id):
        salvar_documento_revisao(
            contrato_id, _CODIGO, _doc_fields(), _rev_fields("0", 1), [], db_path=db_path
        )
        msg = salvar_documento_revisao(
            contrato_id, _CODIGO, _doc_fields(), _rev_fields("0", 1), [], db_path=db_path
        )
        assert "já existe" in msg.lower()

    def test_revisao_duplicada_nao_cria_segunda_entrada(self, db_path, contrato_id):
        salvar_documento_revisao(
            contrato_id, _CODIGO, _doc_fields(), _rev_fields("0", 1), [], db_path=db_path
        )
        salvar_documento_revisao(
            contrato_id, _CODIGO, _doc_fields(), _rev_fields("0", 1), [], db_path=db_path
        )
        with get_connection(db_path) as conn:
            doc = conn.execute("SELECT id FROM documentos WHERE codigo = ?", (_CODIGO,)).fetchone()
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM revisoes WHERE documento_id = ?", (doc["id"],)
            ).fetchone()["n"]
        assert count == 1

    def test_mesma_label_versao_diferente_permite_salvar(self, db_path, contrato_id):
        salvar_documento_revisao(
            contrato_id, _CODIGO, _doc_fields(), _rev_fields("0", 1), [], db_path=db_path
        )
        msg = salvar_documento_revisao(
            contrato_id, _CODIGO, _doc_fields(), _rev_fields("0", 2), [], db_path=db_path
        )
        assert "sucesso" in msg.lower()


# ---------------------------------------------------------------------------
# Cadastro em lote (múltiplos códigos)
# ---------------------------------------------------------------------------

class TestCadastroLote:

    def test_dois_documentos_distintos_salvos(self, db_path, contrato_id):
        msg1 = salvar_documento_revisao(
            contrato_id, _CODIGO,  _doc_fields("Doc A"), _rev_fields(), [], db_path=db_path
        )
        msg2 = salvar_documento_revisao(
            contrato_id, _CODIGO2, _doc_fields("Doc B"), _rev_fields(), [], db_path=db_path
        )
        assert "sucesso" in msg1.lower()
        assert "sucesso" in msg2.lower()

    def test_dados_nao_se_misturam_entre_documentos(self, db_path, contrato_id):
        salvar_documento_revisao(
            contrato_id, _CODIGO,  _doc_fields("Titulo A"), _rev_fields(), [], db_path=db_path
        )
        salvar_documento_revisao(
            contrato_id, _CODIGO2, _doc_fields("Titulo B"), _rev_fields(), [], db_path=db_path
        )
        with get_connection(db_path) as conn:
            doc_a = conn.execute(
                "SELECT titulo FROM documentos WHERE codigo = ?", (_CODIGO,)
            ).fetchone()
            doc_b = conn.execute(
                "SELECT titulo FROM documentos WHERE codigo = ?", (_CODIGO2,)
            ).fetchone()
        assert doc_a["titulo"] == "Titulo A"
        assert doc_b["titulo"] == "Titulo B"

    def test_lote_duplicata_so_bloqueia_o_documento_afetado(self, db_path, contrato_id):
        salvar_documento_revisao(
            contrato_id, _CODIGO, _doc_fields(), _rev_fields("0", 1), [], db_path=db_path
        )
        msg_dup = salvar_documento_revisao(
            contrato_id, _CODIGO, _doc_fields(), _rev_fields("0", 1), [], db_path=db_path
        )
        msg_ok = salvar_documento_revisao(
            contrato_id, _CODIGO2, _doc_fields(), _rev_fields("0", 1), [], db_path=db_path
        )
        assert "já existe" in msg_dup.lower()
        assert "sucesso" in msg_ok.lower()

    def test_contratos_distintos_nao_interferem(self, db_path, contrato_id):
        with get_connection(db_path) as conn:
            contrato2 = conn.execute(
                "INSERT INTO contratos (nome) VALUES (?)", ("Outro Contrato",)
            ).lastrowid
        msg1 = salvar_documento_revisao(
            contrato_id, _CODIGO, _doc_fields("Doc Contrato 1"), _rev_fields(), [], db_path=db_path
        )
        msg2 = salvar_documento_revisao(
            contrato2, _CODIGO, _doc_fields("Doc Contrato 2"), _rev_fields(), [], db_path=db_path
        )
        assert "sucesso" in msg1.lower()
        assert "sucesso" in msg2.lower()
