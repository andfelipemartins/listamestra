"""
tests/test_importers/test_arquivos_importer.py

Testes de integração do ArquivosImporter (core/importers/arquivos_importer.py).

Execute com:
    pytest tests/ -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from core.importers.arquivos_importer import ArquivosImporter
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
            "INSERT INTO documentos (contrato_id, codigo, tipo) VALUES (?, ?, 'DE')",
            (cid, "DE-15.25.00.00-6A1-1001"),
        )
        conn.execute(
            "INSERT INTO documentos (contrato_id, codigo, tipo) VALUES (?, ?, 'DE')",
            (cid, "DE-15.25.00.00-6A1-1002"),
        )
    return db_path, cid


def _importar(db, conteudo):
    db_path, cid = db
    return ArquivosImporter().importar_texto(conteudo, cid, db_path=db_path), db_path, cid


# ---------------------------------------------------------------------------
# Casos básicos
# ---------------------------------------------------------------------------

class TestBasico:

    def test_arquivo_valido_e_inserido(self, db):
        r, db_path, cid = _importar(db, "DE-15.25.00.00-6A1-1001-1-1.pdf\n")
        assert r.novos == 1
        assert r.sem_documento == 0
        assert r.nao_reconhecidos == 0

    def test_arquivo_valido_registrado_no_banco(self, db):
        _importar(db, "DE-15.25.00.00-6A1-1001-1-1.pdf\n")
        db_path, cid = db
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT nome_arquivo, extensao, revisao_detectada FROM arquivos"
            ).fetchone()
        assert row["nome_arquivo"] == "DE-15.25.00.00-6A1-1001-1-1.pdf"
        assert row["extensao"] == "pdf"
        assert row["revisao_detectada"] == "1-1"

    def test_revisao_detectada_formato_antigo(self, db):
        _importar(db, "DE-15.25.00.00-6A1-1001-0.pdf\n")
        db_path, _ = db
        with get_connection(db_path) as conn:
            row = conn.execute("SELECT revisao_detectada FROM arquivos").fetchone()
        assert row["revisao_detectada"] == "0"

    def test_multiplos_arquivos(self, db):
        conteudo = (
            "DE-15.25.00.00-6A1-1001-1-1.pdf\n"
            "DE-15.25.00.00-6A1-1001-1-1.dwg\n"
            "DE-15.25.00.00-6A1-1002-1-1.pdf\n"
        )
        r, *_ = _importar(db, conteudo)
        assert r.novos == 3

    def test_arquivo_sem_documento_correspondente(self, db):
        r, *_ = _importar(db, "DE-15.25.00.00-6A1-9999-1-1.pdf\n")
        assert r.sem_documento == 1
        assert r.novos == 0
        assert "DE-15.25.00.00-6A1-9999" in r.sem_doc_codigos

    def test_nome_invalido_nao_reconhecido(self, db):
        r, *_ = _importar(db, "planilha_controle.xlsx\n")
        assert r.nao_reconhecidos == 1
        assert r.novos == 0
        assert len(r.erros_parse) == 1


# ---------------------------------------------------------------------------
# OBSOLETO
# ---------------------------------------------------------------------------

class TestObsoleto:

    def test_linha_com_obsoleto_ignorada(self, db):
        r, *_ = _importar(db, r"C:\PASTA\OBSOLETO\DE-15.25.00.00-6A1-1001-1-1.pdf")
        assert r.obsoletos_ignorados == 1
        assert r.novos == 0

    def test_obsoleto_case_insensitive(self, db):
        r, *_ = _importar(db, r"C:\pasta\obsoleto\DE-15.25.00.00-6A1-1001-1-1.pdf")
        assert r.obsoletos_ignorados == 1

    def test_arquivo_valido_e_obsoleto_juntos(self, db):
        conteudo = (
            "DE-15.25.00.00-6A1-1001-1-1.pdf\n"
            r"C:\PASTA\OBSOLETO\DE-15.25.00.00-6A1-1001-0-1.pdf" + "\n"
        )
        r, *_ = _importar(db, conteudo)
        assert r.novos == 1
        assert r.obsoletos_ignorados == 1


# ---------------------------------------------------------------------------
# Idempotência
# ---------------------------------------------------------------------------

class TestIdempotencia:

    def test_reimportacao_nao_duplica_registro(self, db):
        conteudo = "DE-15.25.00.00-6A1-1001-1-1.pdf\n"
        _importar(db, conteudo)
        r2, db_path, _ = _importar(db, conteudo)
        assert r2.ja_existentes == 1
        assert r2.novos == 0
        with get_connection(db_path) as conn:
            n = conn.execute("SELECT COUNT(*) FROM arquivos").fetchone()[0]
        assert n == 1

    def test_arquivos_diferentes_sao_inseridos(self, db):
        _importar(db, "DE-15.25.00.00-6A1-1001-1-1.pdf\n")
        r2, db_path, _ = _importar(db, "DE-15.25.00.00-6A1-1001-1-2.pdf\n")
        assert r2.novos == 1
        with get_connection(db_path) as conn:
            n = conn.execute("SELECT COUNT(*) FROM arquivos").fetchone()[0]
        assert n == 2


# ---------------------------------------------------------------------------
# Totais e rastreabilidade
# ---------------------------------------------------------------------------

class TestTotais:

    def test_total_linhas_soma_todas_as_categorias(self, db):
        conteudo = (
            "DE-15.25.00.00-6A1-1001-1-1.pdf\n"   # novo
            "planilha.xlsx\n"                       # não reconhecido
            "DE-15.25.00.00-6A1-9999-1-1.pdf\n"   # sem documento
            r"C:\OBSOLETO\x.pdf" + "\n"             # obsoleto
        )
        r, *_ = _importar(db, conteudo)
        assert r.total_linhas == 4
        assert r.novos + r.nao_reconhecidos + r.sem_documento + r.obsoletos_ignorados == 4

    def test_importacao_registrada_na_tabela(self, db):
        _importar(db, "DE-15.25.00.00-6A1-1001-1-1.pdf\n")
        db_path, cid = db
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT origem, status, total_novos FROM importacoes WHERE contrato_id=?",
                (cid,),
            ).fetchone()
        assert row["origem"] == "arquivos_nomes"
        assert row["status"] == "concluido"
        assert row["total_novos"] == 1

    def test_caminho_completo_preservado_em_arquivos(self, db):
        caminho = r"C:\SharePoint\EXECUTIVO\DE-15.25.00.00-6A1-1001-1-1.pdf"
        _importar(db, caminho + "\n")
        db_path, _ = db
        with get_connection(db_path) as conn:
            row = conn.execute("SELECT caminho FROM arquivos").fetchone()
        assert row["caminho"] == caminho

    def test_arquivo_sem_caminho_tem_caminho_nulo(self, db):
        _importar(db, "DE-15.25.00.00-6A1-1001-1-1.pdf\n")
        db_path, _ = db
        with get_connection(db_path) as conn:
            row = conn.execute("SELECT caminho FROM arquivos").fetchone()
        assert row["caminho"] is None
