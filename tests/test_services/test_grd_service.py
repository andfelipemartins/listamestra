"""
tests/test_services/test_grd_service.py

Testes do GrdService — criação de GRD em lote e listagem de selecionáveis.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scripts"))

from init_db import init_db
from core.repositories.contract_repository import ContractRepository
from core.repositories.documento_repository import DocumentoRepository
from core.repositories.revisao_repository import RevisaoRepository
from core.services.grd_service import GrdService


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    init_db(path, verbose=False)
    return path


@pytest.fixture
def contrato_id(db_path):
    return ContractRepository(db_path).criar_contrato("Contrato A", "Cliente A")


@pytest.fixture
def service(db_path):
    return GrdService(db_path=db_path)


def _doc_rev(db_path, contrato_id, codigo, **rev):
    doc_id = DocumentoRepository(db_path).criar_documento({
        "contrato_id": contrato_id, "codigo": codigo, "tipo": "DE",
        "trecho": rev.get("trecho", "25"), "origem": "teste",
    })
    rev_id = RevisaoRepository(db_path).criar_revisao({
        "documento_id": doc_id, "revisao": 0, "versao": 1, "label_revisao": "0",
        "data_emissao": rev.get("data_emissao", "2025-01-01"),
        "situacao": rev.get("situacao", "APROVADO"),
        "ultima_revisao": 1, "origem": "teste",
    })
    return rev_id


class TestCriarGrd:
    def test_uma_grd_para_multiplos_documentos(self, service, db_path, contrato_id):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        r2 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1002")
        r3 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1003")

        resultado = service.criar_grd(
            contrato_id,
            {"numero_grd": "GRD-001", "data_envio": "2026-06-07", "setor": "Produção"},
            [r1, r2, r3],
        )

        assert resultado.sucesso
        assert resultado.total_itens == 3
        # uma única GRD criada, com 3 itens
        grds = service.listar_grds(contrato_id)
        assert len(grds) == 1
        assert grds[0]["numero_grd"] == "GRD-001"
        assert grds[0]["total_itens"] == 3

    def test_cabecalho_nao_se_repete_por_documento(self, service, db_path, contrato_id):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        r2 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1002")
        service.criar_grd(contrato_id, {"numero_grd": "GRD-XYZ", "setor": "Topografia"}, [r1, r2])
        grds = service.listar_grds(contrato_id)
        # número/setor informados uma vez, válidos para todos os itens
        assert len(grds) == 1
        itens = service.listar_itens(grds[0]["id"])
        assert len(itens) == 2

    def test_sem_selecao_falha(self, service, contrato_id):
        resultado = service.criar_grd(contrato_id, {"numero_grd": "GRD-001"}, [])
        assert not resultado.sucesso
        assert "selecione" in resultado.mensagem.lower()

    def test_revisao_ids_duplicados_sao_deduplicados(self, service, db_path, contrato_id):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        resultado = service.criar_grd(contrato_id, {"numero_grd": "GRD-D"}, [r1, r1, r1])
        assert resultado.sucesso
        assert resultado.total_itens == 1


class TestListarSelecionaveis:
    def test_lista_documentos_enriquecidos(self, service, db_path, contrato_id):
        _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001", situacao="APROVADO")
        docs = service.listar_documentos_selecionaveis(contrato_id)
        assert len(docs) == 1
        d = docs[0]
        assert d["nome_trecho"] == "Ragueb Chohfi"
        assert "status_atual" in d
        assert "revisao_id" in d

    def test_filtro_textual(self, service, db_path, contrato_id):
        _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        _doc_rev(db_path, contrato_id, "MC-15.25.00.00-6A1-1002")
        achados = service.listar_documentos_selecionaveis(contrato_id, "MC-15.25.00.00-6A1-1002")
        assert len(achados) == 1
        assert achados[0]["codigo"] == "MC-15.25.00.00-6A1-1002"

    def test_documento_sem_revisao_nao_aparece(self, service, db_path, contrato_id):
        DocumentoRepository(db_path).criar_documento({
            "contrato_id": contrato_id, "codigo": "DE-15.25.00.00-6A1-9999",
            "tipo": "DE", "origem": "teste",
        })
        assert service.listar_documentos_selecionaveis(contrato_id) == []
