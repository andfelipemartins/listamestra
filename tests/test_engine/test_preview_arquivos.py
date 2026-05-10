"""
tests/test_engine/test_preview_arquivos.py

Testes do gerador de preview de importação de arquivos.

Execute com:
    pytest tests/ -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from core.engine.preview_arquivos import gerar_preview
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
            "INSERT INTO documentos (contrato_id, codigo, tipo, titulo) VALUES (?,?,?,?)",
            (cid, "DE-15.25.00.00-6A1-1001", "DE", "Fundações Bloco A"),
        )
        conn.execute(
            "INSERT INTO documentos (contrato_id, codigo, tipo) VALUES (?,?,?)",
            (cid, "DE-15.25.00.00-6A1-1002", "DE"),
        )
        conn.execute(
            "INSERT INTO documentos_previstos (contrato_id, codigo, tipo, titulo) VALUES (?,?,?,?)",
            (cid, "DE-15.25.00.00-6A1-1002", "DE", "Estrutura Viaduto"),
        )
    return db_path, cid


# ---------------------------------------------------------------------------
# Casos básicos do preview
# ---------------------------------------------------------------------------

class TestPreviewBasico:

    def test_arquivo_novo_aparece_no_preview(self, db):
        db_path, cid = db
        r = gerar_preview("DE-15.25.00.00-6A1-1001-1-1.pdf\n", cid, db_path)
        assert r.total_arquivos_novos == 1
        assert "DE-15.25.00.00-6A1-1001" in r.novos_por_codigo

    def test_titulo_preenchido_do_documento(self, db):
        db_path, cid = db
        r = gerar_preview("DE-15.25.00.00-6A1-1001-1-1.pdf\n", cid, db_path)
        item = r.novos_por_codigo["DE-15.25.00.00-6A1-1001"][0]
        assert item.titulo_atual == "Fundações Bloco A"

    def test_titulo_fallback_de_previstos(self, db):
        """Documento sem titulo em documentos → usa titulo de documentos_previstos."""
        db_path, cid = db
        r = gerar_preview("DE-15.25.00.00-6A1-1002-1-1.pdf\n", cid, db_path)
        item = r.novos_por_codigo["DE-15.25.00.00-6A1-1002"][0]
        assert item.titulo_atual == "Estrutura Viaduto"

    def test_titulo_none_quando_nenhum_disponivel(self, db):
        db_path, cid = db
        with get_connection(db_path) as conn:
            conn.execute(
                "INSERT INTO documentos (contrato_id, codigo, tipo) VALUES (?,?,?)",
                (cid, "DE-15.25.00.00-6A1-1003", "DE"),
            )
        r = gerar_preview("DE-15.25.00.00-6A1-1003-1-1.pdf\n", cid, db_path)
        item = r.novos_por_codigo["DE-15.25.00.00-6A1-1003"][0]
        assert item.titulo_atual is None

    def test_banco_vazio_de_arquivos(self, db):
        db_path, cid = db
        r = gerar_preview("", cid, db_path)
        assert r.vazio

    def test_nao_grava_nada_no_banco(self, db):
        db_path, cid = db
        gerar_preview("DE-15.25.00.00-6A1-1001-1-1.pdf\n", cid, db_path)
        with get_connection(db_path) as conn:
            n = conn.execute("SELECT COUNT(*) FROM arquivos").fetchone()[0]
        assert n == 0


# ---------------------------------------------------------------------------
# Agrupamento por código (PDF + DWG = 1 documento)
# ---------------------------------------------------------------------------

class TestAgrupamento:

    def test_pdf_e_dwg_agrupados_no_mesmo_codigo(self, db):
        db_path, cid = db
        conteudo = (
            "DE-15.25.00.00-6A1-1001-1-1.pdf\n"
            "DE-15.25.00.00-6A1-1001-1-1.dwg\n"
        )
        r = gerar_preview(conteudo, cid, db_path)
        assert r.total_documentos_novos == 1
        assert r.total_arquivos_novos == 2
        arquivos = r.novos_por_codigo["DE-15.25.00.00-6A1-1001"]
        extensoes = {i.extensao for i in arquivos}
        assert extensoes == {"pdf", "dwg"}

    def test_dois_documentos_diferentes(self, db):
        db_path, cid = db
        conteudo = (
            "DE-15.25.00.00-6A1-1001-1-1.pdf\n"
            "DE-15.25.00.00-6A1-1002-1-1.pdf\n"
        )
        r = gerar_preview(conteudo, cid, db_path)
        assert r.total_documentos_novos == 2


# ---------------------------------------------------------------------------
# Categorias de não-novos
# ---------------------------------------------------------------------------

class TestCategorias:

    def test_ja_existente_nao_aparece_como_novo(self, db):
        db_path, cid = db
        ArquivosImporter().importar_texto(
            "DE-15.25.00.00-6A1-1001-1-1.pdf\n", cid, db_path=db_path
        )
        r = gerar_preview("DE-15.25.00.00-6A1-1001-1-1.pdf\n", cid, db_path)
        assert r.total_arquivos_novos == 0
        assert r.ja_existentes == 1

    def test_obsoleto_contado_e_ignorado(self, db):
        db_path, cid = db
        r = gerar_preview(
            r"C:\PASTA\OBSOLETO\DE-15.25.00.00-6A1-1001-1-1.pdf", cid, db_path
        )
        assert r.obsoletos == 1
        assert r.total_arquivos_novos == 0

    def test_sem_documento_no_banco(self, db):
        db_path, cid = db
        r = gerar_preview("DE-15.25.00.00-6A1-9999-1-1.pdf\n", cid, db_path)
        assert "DE-15.25.00.00-6A1-9999" in r.sem_documento
        assert r.total_arquivos_novos == 0

    def test_sem_documento_sem_duplicata_no_codigo(self, db):
        """PDF e DWG do mesmo código ausente → aparece uma única vez em sem_documento."""
        db_path, cid = db
        conteudo = (
            "DE-15.25.00.00-6A1-9999-1-1.pdf\n"
            "DE-15.25.00.00-6A1-9999-1-1.dwg\n"
        )
        r = gerar_preview(conteudo, cid, db_path)
        assert r.sem_documento.count("DE-15.25.00.00-6A1-9999") == 1

    def test_nao_reconhecido_contado(self, db):
        db_path, cid = db
        r = gerar_preview("planilha.xlsx\n", cid, db_path)
        assert len(r.nao_reconhecidos) == 1
        assert "planilha.xlsx" in r.nao_reconhecidos


# ---------------------------------------------------------------------------
# Fluxo completo: preview → confirmar_preview
# ---------------------------------------------------------------------------

class TestFluxoCompleto:

    def test_confirmar_salva_arquivos(self, db):
        db_path, cid = db
        preview = gerar_preview("DE-15.25.00.00-6A1-1001-1-1.pdf\n", cid, db_path)
        titulos = {"DE-15.25.00.00-6A1-1001": "Fundações Bloco A Revisado"}
        r = ArquivosImporter().confirmar_preview(preview, titulos, cid, db_path=db_path)
        assert r.novos == 1
        with get_connection(db_path) as conn:
            n = conn.execute("SELECT COUNT(*) FROM arquivos").fetchone()[0]
        assert n == 1

    def test_confirmar_atualiza_titulo_documento(self, db):
        db_path, cid = db
        preview = gerar_preview("DE-15.25.00.00-6A1-1001-1-1.pdf\n", cid, db_path)
        titulos = {"DE-15.25.00.00-6A1-1001": "Novo Objeto Confirmado"}
        ArquivosImporter().confirmar_preview(preview, titulos, cid, db_path=db_path)
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT titulo FROM documentos WHERE codigo = ?",
                ("DE-15.25.00.00-6A1-1001",),
            ).fetchone()
        assert row["titulo"] == "Novo Objeto Confirmado"

    def test_confirmar_nao_atualiza_titulo_se_igual(self, db):
        db_path, cid = db
        preview = gerar_preview("DE-15.25.00.00-6A1-1001-1-1.pdf\n", cid, db_path)
        titulos = {"DE-15.25.00.00-6A1-1001": "Fundações Bloco A"}  # mesmo título
        ArquivosImporter().confirmar_preview(preview, titulos, cid, db_path=db_path)
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT titulo FROM documentos WHERE codigo = ?",
                ("DE-15.25.00.00-6A1-1001",),
            ).fetchone()
        assert row["titulo"] == "Fundações Bloco A"

    def test_confirmar_pdf_e_dwg_do_mesmo_documento(self, db):
        db_path, cid = db
        conteudo = (
            "DE-15.25.00.00-6A1-1001-1-1.pdf\n"
            "DE-15.25.00.00-6A1-1001-1-1.dwg\n"
        )
        preview = gerar_preview(conteudo, cid, db_path)
        titulos = {"DE-15.25.00.00-6A1-1001": "Fundações Bloco A"}
        r = ArquivosImporter().confirmar_preview(preview, titulos, cid, db_path=db_path)
        assert r.novos == 2
        with get_connection(db_path) as conn:
            n = conn.execute("SELECT COUNT(*) FROM arquivos").fetchone()[0]
        assert n == 2


# ---------------------------------------------------------------------------
# Validação de Objeto obrigatório no backend
# ---------------------------------------------------------------------------

class TestValidacaoBackend:

    def test_objeto_em_branco_levanta_erro(self, db):
        db_path, cid = db
        preview = gerar_preview("DE-15.25.00.00-6A1-1001-1-1.pdf\n", cid, db_path)
        titulos = {"DE-15.25.00.00-6A1-1001": ""}  # em branco
        with pytest.raises(ValueError, match="Objeto obrigatório"):
            ArquivosImporter().confirmar_preview(preview, titulos, cid, db_path=db_path)

    def test_objeto_ausente_levanta_erro(self, db):
        db_path, cid = db
        preview = gerar_preview("DE-15.25.00.00-6A1-1001-1-1.pdf\n", cid, db_path)
        titulos = {}  # código não presente no dict
        with pytest.raises(ValueError, match="Objeto obrigatório"):
            ArquivosImporter().confirmar_preview(preview, titulos, cid, db_path=db_path)

    def test_objeto_so_espacos_levanta_erro(self, db):
        db_path, cid = db
        preview = gerar_preview("DE-15.25.00.00-6A1-1001-1-1.pdf\n", cid, db_path)
        titulos = {"DE-15.25.00.00-6A1-1001": "   "}
        with pytest.raises(ValueError):
            ArquivosImporter().confirmar_preview(preview, titulos, cid, db_path=db_path)

    def test_objeto_valido_nao_levanta_erro(self, db):
        db_path, cid = db
        preview = gerar_preview("DE-15.25.00.00-6A1-1001-1-1.pdf\n", cid, db_path)
        titulos = {"DE-15.25.00.00-6A1-1001": "Fundações Bloco A"}
        r = ArquivosImporter().confirmar_preview(preview, titulos, cid, db_path=db_path)
        assert r.novos == 1


# ---------------------------------------------------------------------------
# Audit trail: inconsistencias persistidas ao confirmar
# ---------------------------------------------------------------------------

class TestAuditTrailConfirmar:

    def test_sem_documento_salvo_em_inconsistencias(self, db):
        db_path, cid = db
        conteudo = (
            "DE-15.25.00.00-6A1-1001-1-1.pdf\n"   # válido
            "DE-15.25.00.00-6A1-9999-1-1.pdf\n"   # sem documento
        )
        preview = gerar_preview(conteudo, cid, db_path)
        titulos = {"DE-15.25.00.00-6A1-1001": "Fundações Bloco A"}
        ArquivosImporter().confirmar_preview(preview, titulos, cid, db_path=db_path)
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT tipo_inconsistencia, documento_codigo FROM inconsistencias"
            ).fetchone()
        assert row["tipo_inconsistencia"] == "arquivo_sem_documento"
        assert row["documento_codigo"] == "DE-15.25.00.00-6A1-9999"

    def test_nao_reconhecido_salvo_em_inconsistencias(self, db):
        db_path, cid = db
        conteudo = (
            "DE-15.25.00.00-6A1-1001-1-1.pdf\n"
            "planilha_ruim.xlsx\n"
        )
        preview = gerar_preview(conteudo, cid, db_path)
        titulos = {"DE-15.25.00.00-6A1-1001": "Fundações Bloco A"}
        ArquivosImporter().confirmar_preview(preview, titulos, cid, db_path=db_path)
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT tipo_inconsistencia FROM inconsistencias"
            ).fetchone()
        assert row["tipo_inconsistencia"] == "arquivo_nao_reconhecido"

    def test_sem_erros_sem_inconsistencias(self, db):
        db_path, cid = db
        preview = gerar_preview("DE-15.25.00.00-6A1-1001-1-1.pdf\n", cid, db_path)
        titulos = {"DE-15.25.00.00-6A1-1001": "Fundações Bloco A"}
        ArquivosImporter().confirmar_preview(preview, titulos, cid, db_path=db_path)
        with get_connection(db_path) as conn:
            n = conn.execute("SELECT COUNT(*) FROM inconsistencias").fetchone()[0]
        assert n == 0
