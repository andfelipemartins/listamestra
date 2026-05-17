"""
tests/test_services/test_documento_service.py

Testes do DocumentoService.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scripts"),
)

from init_db import init_db
from db.connection import get_connection
from core.repositories.contract_repository import ContractRepository
from core.repositories.documento_repository import DocumentoRepository
from core.repositories.revisao_repository import RevisaoRepository
from core.services.documento_service import DocumentoService


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
    return ContractRepository(db_path).criar_contrato("Contrato Teste", "Cliente X")


@pytest.fixture
def doc_repo(db_path):
    return DocumentoRepository(db_path)


@pytest.fixture
def rev_repo(db_path):
    return RevisaoRepository(db_path)


@pytest.fixture
def service(doc_repo, rev_repo):
    return DocumentoService(doc_repo, rev_repo)


def _criar_doc(doc_repo, contrato_id, codigo, **kwargs):
    return doc_repo.criar_documento(
        {
            "contrato_id": contrato_id,
            "codigo": codigo,
            "tipo": kwargs.get("tipo", "DE"),
            "titulo": kwargs.get("titulo"),
            "disciplina": kwargs.get("disciplina"),
            "trecho": kwargs.get("trecho", "25"),
            "nome_trecho": kwargs.get("nome_trecho"),
            "origem": kwargs.get("origem", "teste"),
        }
    )


def _criar_revisao(rev_repo, doc_id, **kwargs):
    return rev_repo.criar_revisao(
        {
            "documento_id": doc_id,
            "revisao": kwargs.get("revisao", 0),
            "versao": kwargs.get("versao", 1),
            "label_revisao": kwargs.get("label_revisao", "00"),
            "emissao_inicial": kwargs.get("emissao_inicial"),
            "data_emissao": kwargs.get("data_emissao"),
            "situacao": kwargs.get("situacao"),
            "ultima_revisao": int(kwargs.get("ultima_revisao", 0)),
            "origem": "teste",
        }
    )


def _criar_previsto(db_path, contrato_id, codigo, **kwargs):
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO documentos_previstos (contrato_id, codigo, tipo, titulo, disciplina, trecho, ativo)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (
                contrato_id,
                codigo,
                kwargs.get("tipo", "DE"),
                kwargs.get("titulo"),
                kwargs.get("disciplina"),
                kwargs.get("trecho"),
            ),
        )


# ---------------------------------------------------------------------------
# Busca básica
# ---------------------------------------------------------------------------

class TestBuscaDocumento:

    def test_buscar_por_codigo_existente(self, service, doc_repo, contrato_id):
        _criar_doc(doc_repo, contrato_id, "DE-15.25.00.00-6A1-1001", titulo="Planta Geral")

        doc = service.buscar_documento_por_codigo(contrato_id, "DE-15.25.00.00-6A1-1001")

        assert doc is not None
        assert doc["codigo"] == "DE-15.25.00.00-6A1-1001"
        assert doc["titulo"] == "Planta Geral"

    def test_buscar_por_codigo_inexistente_retorna_none(self, service, contrato_id):
        doc = service.buscar_documento_por_codigo(contrato_id, "DE-15.00.00.00-6A1-9999")

        assert doc is None

    def test_buscar_por_id_existente(self, service, doc_repo, contrato_id):
        doc_id = _criar_doc(doc_repo, contrato_id, "DE-15.25.00.00-6A1-1002")

        doc = service.buscar_documento_por_id(doc_id)

        assert doc is not None
        assert doc["id"] == doc_id

    def test_buscar_por_id_inexistente_retorna_none(self, service):
        doc = service.buscar_documento_por_id(999_999)

        assert doc is None


# ---------------------------------------------------------------------------
# Previsto (documentos_previstos)
# ---------------------------------------------------------------------------

class TestBuscarPrevisto:

    def test_buscar_previsto_existente(self, service, db_path, contrato_id):
        _criar_previsto(
            db_path, contrato_id, "DE-15.25.00.00-6A1-1001",
            titulo="Titulo do ID", disciplina="B3", trecho="25",
        )

        previsto = service.buscar_previsto(contrato_id, "DE-15.25.00.00-6A1-1001")

        assert previsto is not None
        assert previsto["titulo"] == "Titulo do ID"
        assert previsto["disciplina"] == "B3"
        assert previsto["trecho"] == "25"

    def test_buscar_previsto_inexistente_retorna_none(self, service, contrato_id):
        previsto = service.buscar_previsto(contrato_id, "DE-15.00.00.00-6A1-9999")

        assert previsto is None


# ---------------------------------------------------------------------------
# Revisões
# ---------------------------------------------------------------------------

class TestRevisoes:

    def test_listar_revisoes_documento_sem_revisao(self, service, doc_repo, contrato_id):
        doc_id = _criar_doc(doc_repo, contrato_id, "DE-15.25.00.00-6A1-1003")

        revisoes = service.listar_revisoes_do_documento(doc_id)

        assert revisoes == []

    def test_listar_revisoes_documento_com_uma_revisao(self, service, doc_repo, rev_repo, contrato_id):
        doc_id = _criar_doc(doc_repo, contrato_id, "DE-15.25.00.00-6A1-1004")
        _criar_revisao(rev_repo, doc_id, label_revisao="00", ultima_revisao=1)

        revisoes = service.listar_revisoes_do_documento(doc_id)

        assert len(revisoes) == 1
        assert revisoes[0]["label_revisao"] == "00"

    def test_listar_revisoes_ordenadas_cronologicamente(self, service, doc_repo, rev_repo, contrato_id):
        doc_id = _criar_doc(doc_repo, contrato_id, "DE-15.25.00.00-6A1-1005")
        _criar_revisao(rev_repo, doc_id, revisao=1, label_revisao="01", data_emissao="2025-03-01", ultima_revisao=0)
        _criar_revisao(rev_repo, doc_id, revisao=0, label_revisao="00", data_emissao="2025-01-01", ultima_revisao=1)

        revisoes = service.listar_revisoes_do_documento(doc_id)

        assert len(revisoes) == 2
        assert revisoes[0]["label_revisao"] == "00"
        assert revisoes[1]["label_revisao"] == "01"


# ---------------------------------------------------------------------------
# Carregar detalhe
# ---------------------------------------------------------------------------

class TestCarregarDetalhe:

    def test_detalhe_documento_inexistente_retorna_none(self, service):
        assert service.carregar_detalhe_documento(999_999) is None

    def test_detalhe_sem_revisao(self, service, doc_repo, contrato_id):
        doc_id = _criar_doc(doc_repo, contrato_id, "DE-15.25.00.00-6A1-2001", titulo="Sem Rev")

        detalhe = service.carregar_detalhe_documento(doc_id)

        assert detalhe is not None
        assert detalhe["documento"]["titulo"] == "Sem Rev"
        assert detalhe["revisoes"] == []
        assert detalhe["ultima_revisao"] is None
        assert detalhe["status_atual"] == "Em Elaboração"

    def test_detalhe_com_multiplas_revisoes(self, service, doc_repo, rev_repo, contrato_id):
        doc_id = _criar_doc(doc_repo, contrato_id, "DE-15.25.00.00-6A1-2002")
        _criar_revisao(rev_repo, doc_id, revisao=0, label_revisao="00", data_emissao="2025-01-01", ultima_revisao=0)
        _criar_revisao(
            rev_repo, doc_id, revisao=1, label_revisao="01", data_emissao="2025-06-01",
            situacao="APROVADO", ultima_revisao=1,
        )

        detalhe = service.carregar_detalhe_documento(doc_id)

        assert len(detalhe["revisoes"]) == 2
        assert detalhe["ultima_revisao"]["label_revisao"] == "01"
        assert detalhe["status_atual"] == "Aprovado"

    def test_detalhe_ultima_revisao_aprovada(self, service, doc_repo, rev_repo, contrato_id):
        doc_id = _criar_doc(doc_repo, contrato_id, "DE-15.25.00.00-6A1-2003")
        _criar_revisao(
            rev_repo, doc_id, data_emissao="2025-05-01",
            situacao="APROVADO", ultima_revisao=1,
        )

        detalhe = service.carregar_detalhe_documento(doc_id)

        assert detalhe["status_atual"] == "Aprovado"


# ---------------------------------------------------------------------------
# Enriquecimento e exibição
# ---------------------------------------------------------------------------

class TestEnriquecimento:

    def test_enriquecer_documento_adiciona_nome_trecho(self, service):
        doc = {"id": 1, "codigo": "X", "trecho": "25", "situacao": None, "data_emissao": None}

        resultado = service.enriquecer_documento(doc)

        assert resultado["nome_trecho"] == "Ragueb Chohfi"

    def test_enriquecer_documento_trecho_desconhecido_mantem_codigo(self, service):
        doc = {"id": 1, "codigo": "X", "trecho": "99", "situacao": None, "data_emissao": None}

        resultado = service.enriquecer_documento(doc)

        assert resultado["nome_trecho"] == "99"

    def test_enriquecer_documento_sem_trecho(self, service):
        doc = {"id": 1, "codigo": "X", "trecho": None, "situacao": None, "data_emissao": None}

        resultado = service.enriquecer_documento(doc)

        assert resultado["nome_trecho"] == ""

    def test_enriquecer_documento_disciplina_do_campo(self, service):
        doc = {
            "id": 1, "codigo": "DE-15.25.00.00-6A1-1001",
            "trecho": "25", "disciplina": "A1",
            "situacao": None, "data_emissao": None,
        }

        resultado = service.enriquecer_documento(doc)

        assert resultado["disciplina_display"] == "A1"

    def test_enriquecer_documento_disciplina_fallback_do_codigo(self, service):
        doc = {
            "id": 1, "codigo": "DE-15.25.00.00-6A1-1001",
            "trecho": "25", "disciplina": None,
            "situacao": None, "data_emissao": None,
        }

        resultado = service.enriquecer_documento(doc)

        assert resultado["disciplina_display"] == "A1"

    def test_enriquecer_documento_nao_modifica_original(self, service):
        doc = {"id": 1, "codigo": "X", "trecho": "25", "situacao": None, "data_emissao": None}

        service.enriquecer_documento(doc)

        assert "nome_trecho" not in doc


class TestObterExibicao:

    def test_obter_titulo_do_doc(self, service):
        doc = {"titulo": "Planta Baixa"}
        assert service.obter_titulo_exibicao(doc) == "Planta Baixa"

    def test_obter_titulo_fallback_previsto(self, service):
        doc = {"titulo": None}
        previsto = {"titulo": "Titulo do ID"}
        assert service.obter_titulo_exibicao(doc, previsto) == "Titulo do ID"

    def test_obter_titulo_vazio_sem_previsto(self, service):
        doc = {"titulo": None}
        assert service.obter_titulo_exibicao(doc) == ""

    def test_obter_trecho_do_doc(self, service):
        doc = {"trecho": "25", "codigo": "DE-15.25.00.00-6A1-1001"}
        resultado = service.obter_trecho_exibicao(doc)
        assert "25" in resultado
        assert "Ragueb Chohfi" in resultado

    def test_obter_trecho_fallback_previsto(self, service):
        doc = {"trecho": None, "codigo": "X"}
        previsto = {"trecho": "19"}
        resultado = service.obter_trecho_exibicao(doc, previsto)
        assert "19" in resultado
        assert "Oratório" in resultado

    def test_obter_trecho_fallback_parser(self, service):
        doc = {"trecho": None, "codigo": "DE-15.23.00.00-6A1-1001"}
        resultado = service.obter_trecho_exibicao(doc)
        assert "23" in resultado

    def test_obter_trecho_vazio_sem_dado(self, service):
        doc = {"trecho": None, "codigo": "INVALIDO"}
        assert service.obter_trecho_exibicao(doc) == ""

    def test_obter_disciplina_do_doc(self, service):
        doc = {"disciplina": "B3", "codigo": "X"}
        resultado = service.obter_disciplina_exibicao(doc)
        assert "B3" in resultado

    def test_obter_disciplina_fallback_previsto(self, service):
        doc = {"disciplina": None, "codigo": "X"}
        previsto = {"disciplina": "A1"}
        resultado = service.obter_disciplina_exibicao(doc, previsto)
        assert "A1" in resultado

    def test_obter_disciplina_fallback_parser(self, service):
        doc = {"disciplina": None, "codigo": "DE-15.25.00.00-6A1-1001"}
        resultado = service.obter_disciplina_exibicao(doc)
        assert "A1" in resultado

    def test_obter_disciplina_vazia_sem_dado(self, service):
        doc = {"disciplina": None, "codigo": "INVALIDO"}
        assert service.obter_disciplina_exibicao(doc) == ""


# ---------------------------------------------------------------------------
# Resumo e listagem
# ---------------------------------------------------------------------------

class TestMontarResumo:

    def test_montar_resumo_campos_obrigatorios(self, service):
        doc = {
            "id": 42, "codigo": "DE-15.25.00.00-6A1-1001",
            "tipo": "DE", "titulo": "Planta Geral",
            "nome_trecho": "Ragueb Chohfi",
            "disciplina_display": "A1",
            "status_atual": "Aprovado",
        }

        resumo = service.montar_resumo_documento(doc)

        assert resumo["id"] == 42
        assert resumo["codigo"] == "DE-15.25.00.00-6A1-1001"
        assert resumo["tipo"] == "DE"
        assert resumo["titulo"] == "Planta Geral"
        assert resumo["nome_trecho"] == "Ragueb Chohfi"
        assert resumo["disciplina_display"] == "A1"
        assert resumo["status_atual"] == "Aprovado"

    def test_montar_resumo_fallback_campos_ausentes(self, service):
        doc = {"id": 1, "codigo": "X", "tipo": None, "titulo": None}

        resumo = service.montar_resumo_documento(doc)

        assert resumo["tipo"] == "—"
        assert resumo["titulo"] == "(sem título)"
        assert resumo["nome_trecho"] == "—"
        assert resumo["disciplina_display"] == "—"
        assert resumo["status_atual"] == "—"


class TestListagemDocumentos:

    def test_listar_documentos_enriquecidos_vazio(self, service, contrato_id):
        assert service.listar_documentos_enriquecidos(contrato_id) == []

    def test_listar_documentos_enriquecidos_com_dados(
        self, service, doc_repo, contrato_id
    ):
        _criar_doc(doc_repo, contrato_id, "DE-15.25.00.00-6A1-3001", trecho="25")

        docs = service.listar_documentos_enriquecidos(contrato_id)

        assert len(docs) == 1
        assert "nome_trecho" in docs[0]
        assert "disciplina_display" in docs[0]
        assert "status_atual" in docs[0]
        assert docs[0]["nome_trecho"] == "Ragueb Chohfi"

    def test_buscar_documentos_para_consulta_sem_filtro(
        self, service, doc_repo, contrato_id
    ):
        _criar_doc(doc_repo, contrato_id, "DE-15.25.00.00-6A1-3002")
        _criar_doc(doc_repo, contrato_id, "MC-15.25.00.00-6A1-3003", tipo="MC")

        docs = service.buscar_documentos_para_consulta(contrato_id)

        assert len(docs) == 2

    def test_buscar_documentos_para_consulta_com_filtro(
        self, service, doc_repo, contrato_id
    ):
        _criar_doc(doc_repo, contrato_id, "DE-15.25.00.00-6A1-3004", tipo="DE")
        _criar_doc(doc_repo, contrato_id, "MC-15.25.00.00-6A1-3005", tipo="MC")

        docs = service.buscar_documentos_para_consulta(contrato_id, filtros="MC")

        assert len(docs) == 1
        assert docs[0]["tipo"] == "MC"
