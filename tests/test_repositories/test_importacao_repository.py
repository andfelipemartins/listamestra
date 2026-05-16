"""
tests/test_repositories/test_importacao_repository.py

Testes do ImportacaoRepository.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scripts"))

from init_db import init_db
from core.repositories.contract_repository import ContractRepository
from core.repositories.importacao_repository import ImportacaoRepository


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    init_db(path, verbose=False)
    return path


@pytest.fixture
def contrato_id(db_path):
    return ContractRepository(db_path).criar_contrato("Contrato", "Cliente")


@pytest.fixture
def repo(db_path):
    return ImportacaoRepository(db_path)


class TestImportacaoRepository:

    def test_registrar_importacao(self, repo, contrato_id):
        imp_id = repo.registrar_importacao(
            contrato_id=contrato_id,
            origem="lista_documentos",
            arquivo_importado="lista.xlsx",
            total_registros=10,
        )

        row = repo.buscar_importacao_por_id(imp_id)

        assert row["contrato_id"] == contrato_id
        assert row["origem"] == "lista_documentos"
        assert row["arquivo_importado"] == "lista.xlsx"
        assert row["total_registros"] == 10
        assert row["status"] == "em_andamento"

    def test_finalizar_importacao(self, repo, contrato_id):
        imp_id = repo.registrar_importacao(
            contrato_id=contrato_id,
            origem="id_documentos",
            arquivo_importado="id.xlsx",
            total_registros=5,
        )

        repo.finalizar_importacao(
            importacao_id=imp_id,
            total_erros=1,
            total_novos=2,
            total_atualizados=3,
        )

        row = repo.buscar_importacao_por_id(imp_id)
        assert row["total_erros"] == 1
        assert row["total_novos"] == 2
        assert row["total_atualizados"] == 3
        assert row["status"] == "concluido"
        assert row["confirmado_em"] is not None

    def test_listar_historico_importacoes_ordena_por_mais_recente(self, repo, contrato_id):
        primeiro = repo.registrar_importacao(contrato_id, "lista", "a.xlsx", 1)
        segundo = repo.registrar_importacao(contrato_id, "id", "b.xlsx", 1)

        historico = repo.listar_historico_importacoes(contrato_id)

        assert [h["arquivo_importado"] for h in historico] == ["b.xlsx", "a.xlsx"]
        assert historico[0]["origem"] == "id"
        assert primeiro < segundo

    def test_listar_historico_importacoes_respeita_limite(self, repo, contrato_id):
        repo.registrar_importacao(contrato_id, "lista", "a.xlsx", 1)
        repo.registrar_importacao(contrato_id, "lista", "b.xlsx", 1)
        repo.registrar_importacao(contrato_id, "lista", "c.xlsx", 1)

        historico = repo.listar_historico_importacoes(contrato_id, limite=2)

        assert [h["arquivo_importado"] for h in historico] == ["c.xlsx", "b.xlsx"]

    def test_obter_ultima_importacao_retorna_apenas_concluida(self, repo, contrato_id):
        repo.registrar_importacao(contrato_id, "lista", "pendente.xlsx", 1)
        concluida = repo.registrar_importacao(contrato_id, "lista", "ok.xlsx", 1)
        repo.finalizar_importacao(concluida, total_erros=0, total_novos=1, total_atualizados=0)

        ultima = repo.obter_ultima_importacao(contrato_id)

        assert ultima["arquivo_importado"] == "ok.xlsx"
        assert ultima["total_novos"] == 1

    def test_contar_importacoes_por_contrato(self, repo, db_path, contrato_id):
        outro = ContractRepository(db_path).criar_contrato("Outro", "")
        repo.registrar_importacao(contrato_id, "lista", "a.xlsx", 1)
        repo.registrar_importacao(contrato_id, "lista", "b.xlsx", 1)
        repo.registrar_importacao(outro, "lista", "c.xlsx", 1)

        assert repo.contar_importacoes(contrato_id) == 2
        assert repo.contar_importacoes() == 3

    def test_listar_importacoes_filtra_por_status(self, repo, contrato_id):
        repo.registrar_importacao(contrato_id, "lista", "pendente.xlsx", 1)
        concluida = repo.registrar_importacao(contrato_id, "lista", "ok.xlsx", 1)
        repo.finalizar_importacao(concluida, total_erros=0, total_novos=1, total_atualizados=0)

        rows = repo.listar_importacoes(contrato_id=contrato_id, status="concluido")

        assert len(rows) == 1
        assert rows[0]["arquivo_importado"] == "ok.xlsx"
