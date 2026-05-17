"""
tests/test_repositories/test_revisao_repository.py

Testes do RevisaoRepository.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scripts"))

from init_db import init_db
from db.connection import get_connection
from core.repositories.contract_repository import ContractRepository
from core.repositories.documento_repository import DocumentoRepository
from core.repositories.revisao_repository import RevisaoRepository


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    init_db(path, verbose=False)
    return path


@pytest.fixture
def contrato_id(db_path):
    return ContractRepository(db_path).criar_contrato("Contrato A", "Cliente A")


@pytest.fixture
def doc_repo(db_path):
    return DocumentoRepository(db_path)


@pytest.fixture
def repo(db_path):
    return RevisaoRepository(db_path)


@pytest.fixture
def doc_id(doc_repo, contrato_id):
    return doc_repo.criar_documento(
        {
            "contrato_id": contrato_id,
            "codigo": "DE-15.25.00.00-6A1-1001",
            "tipo": "DE",
            "origem": "teste",
        }
    )


def _criar_rev(repo, doc_id, label, versao=1, **kwargs):
    try:
        revisao_int = int(label)
    except (ValueError, TypeError):
        revisao_int = None
    return repo.criar_revisao(
        {
            "documento_id": doc_id,
            "revisao": revisao_int,
            "versao": versao,
            "label_revisao": label,
            "data_emissao": kwargs.get("data_emissao"),
            "situacao": kwargs.get("situacao"),
            "ultima_revisao": kwargs.get("ultima_revisao", 0),
            "origem": kwargs.get("origem", "teste"),
        }
    )


class TestRevisaoRepositoryEscrita:

    def test_criar_revisao_retorna_id(self, repo, doc_id):
        rev_id = _criar_rev(repo, doc_id, "0")

        assert rev_id > 0
        rev = repo.buscar_por_id(rev_id)
        assert rev["documento_id"] == doc_id
        assert rev["label_revisao"] == "0"

    def test_criar_revisao_exige_documento_id(self, repo):
        with pytest.raises(ValueError):
            repo.criar_revisao({"label_revisao": "0", "versao": 1})

    def test_atualizar_revisao_sobrescreve(self, repo, doc_id):
        rev_id = _criar_rev(repo, doc_id, "0", situacao="EM ANALISE")

        repo.atualizar_revisao(rev_id, {"situacao": "APROVADO"})

        assert repo.buscar_por_id(rev_id)["situacao"] == "APROVADO"

    def test_atualizar_emissao_inicial(self, repo, doc_id):
        rev_id = _criar_rev(repo, doc_id, "0")

        repo.atualizar_emissao_inicial(rev_id, "EMISSÃO INICIAL")

        assert repo.buscar_por_id(rev_id)["emissao_inicial"] == "EMISSÃO INICIAL"

    def test_marcar_como_ultima_e_desmarcar(self, repo, doc_id):
        primeiro = _criar_rev(repo, doc_id, "0", ultima_revisao=1)
        segundo = _criar_rev(repo, doc_id, "1")

        repo.desmarcar_ultimas_por_documento(doc_id)
        repo.marcar_como_ultima(segundo)

        assert repo.buscar_por_id(primeiro)["ultima_revisao"] == 0
        assert repo.buscar_por_id(segundo)["ultima_revisao"] == 1

    def test_recalcular_ultimas_por_contrato(
        self, repo, doc_repo, contrato_id, doc_id
    ):
        outro_doc = doc_repo.criar_documento(
            {
                "contrato_id": contrato_id,
                "codigo": "DE-15.25.00.00-6A1-1002",
                "tipo": "DE",
            }
        )
        _criar_rev(repo, doc_id, "0", data_emissao="2024-01-01")
        ult_doc1 = _criar_rev(repo, doc_id, "1", data_emissao="2024-06-01")
        ult_doc2 = _criar_rev(repo, outro_doc, "0", data_emissao="2024-02-01")

        repo.recalcular_ultimas_por_contrato(contrato_id)

        assert repo.buscar_por_id(ult_doc1)["ultima_revisao"] == 1
        assert repo.buscar_por_id(ult_doc2)["ultima_revisao"] == 1
        # As outras revisões devem estar marcadas como não-ultima
        outras = [
            r for r in repo.listar_por_contrato(contrato_id)
            if r["id"] not in (ult_doc1, ult_doc2)
        ]
        assert all(r["ultima_revisao"] == 0 for r in outras)


class TestRevisaoRepositoryLeitura:

    def test_listar_por_documento_ordena_cronologicamente(self, repo, doc_id):
        _criar_rev(repo, doc_id, "1", data_emissao="2024-06-01")
        _criar_rev(repo, doc_id, "0", data_emissao="2024-01-01")
        _criar_rev(repo, doc_id, "2", data_emissao=None)

        labels = [r["label_revisao"] for r in repo.listar_por_documento(doc_id)]

        assert labels == ["0", "1", "2"]

    def test_listar_resumo_por_documento_traz_apenas_colunas_basicas(
        self, repo, doc_id
    ):
        _criar_rev(repo, doc_id, "0", situacao="EM ANALISE")

        rows = repo.listar_resumo_por_documento(doc_id)

        assert set(rows[0].keys()) == {
            "label_revisao",
            "versao",
            "emissao_inicial",
            "data_emissao",
            "situacao",
        }
        assert rows[0]["situacao"] == "EM ANALISE"

    def test_buscar_ultima_revisao_usa_data_emissao(self, repo, doc_id):
        _criar_rev(repo, doc_id, "0", data_emissao="2024-01-01")
        nova = _criar_rev(repo, doc_id, "1", data_emissao="2024-06-01")

        ultima = repo.buscar_ultima_revisao(doc_id)

        assert ultima["id"] == nova

    def test_buscar_ultima_revisao_sem_data_fallback_para_id(self, repo, doc_id):
        _criar_rev(repo, doc_id, "0")
        nova = _criar_rev(repo, doc_id, "1")

        ultima = repo.buscar_ultima_revisao(doc_id)

        assert ultima["id"] == nova

    def test_existe_revisao(self, repo, doc_id):
        _criar_rev(repo, doc_id, "0", versao=1)

        assert repo.existe_revisao(doc_id, "0", 1) is True
        assert repo.existe_revisao(doc_id, "0", 2) is False

    def test_buscar_por_label_versao(self, repo, doc_id):
        rev_id = _criar_rev(repo, doc_id, "A1", versao=2)

        rev = repo.buscar_por_label_versao(doc_id, "A1", 2)

        assert rev["id"] == rev_id

    def test_listar_para_recalculo_traz_campos_minimos(self, repo, doc_id):
        _criar_rev(repo, doc_id, "0", situacao="APROVADO", data_emissao="2024-01-01")

        rows = repo.listar_para_recalculo(doc_id)

        assert set(rows[0].keys()) == {"id", "data_emissao", "situacao"}

    def test_listar_por_contrato_inclui_codigo_do_documento(
        self, repo, doc_repo, contrato_id, doc_id
    ):
        _criar_rev(repo, doc_id, "0")
        outro_doc = doc_repo.criar_documento(
            {
                "contrato_id": contrato_id,
                "codigo": "DE-15.25.00.00-6A1-1002",
                "tipo": "DE",
            }
        )
        _criar_rev(repo, outro_doc, "0")

        revs = repo.listar_por_contrato(contrato_id)

        codigos = {r["codigo"] for r in revs}
        assert codigos == {
            "DE-15.25.00.00-6A1-1001",
            "DE-15.25.00.00-6A1-1002",
        }


class TestRevisaoRepositoryContagem:

    def test_contar_por_contrato(
        self, repo, doc_repo, contrato_id, doc_id
    ):
        _criar_rev(repo, doc_id, "0")
        _criar_rev(repo, doc_id, "1")
        outro_doc = doc_repo.criar_documento(
            {
                "contrato_id": contrato_id,
                "codigo": "DE-15.25.00.00-6A1-1002",
                "tipo": "DE",
            }
        )
        _criar_rev(repo, outro_doc, "0")

        assert repo.contar_por_contrato(contrato_id) == 3

    def test_contar_por_documento(self, repo, doc_id):
        _criar_rev(repo, doc_id, "0")
        _criar_rev(repo, doc_id, "1")

        assert repo.contar_por_documento(doc_id) == 2


class TestRevisaoRepositoryConexaoExterna:

    def test_aceita_conexao_externa(self, repo, db_path, doc_id):
        _criar_rev(repo, doc_id, "0")

        with get_connection(db_path) as conn:
            revs = repo.listar_por_documento(doc_id, conn=conn)

        assert len(revs) == 1
