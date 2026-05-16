"""
tests/test_repositories/test_contract_repository.py

Testes do ContractRepository.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scripts"))

from init_db import init_db
from db.connection import get_connection
from core.repositories.contract_repository import ContractRepository


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    init_db(path, verbose=False)
    return path


@pytest.fixture
def repo(db_path):
    return ContractRepository(db_path)


class TestContractRepository:

    def test_verificar_banco_existente(self, repo):
        assert repo.verificar_banco() is True

    def test_criar_contrato(self, repo):
        cid = repo.criar_contrato("Contrato A", "Cliente A")

        contrato = repo.obter_contrato_por_id(cid)
        assert contrato["nome"] == "Contrato A"
        assert contrato["cliente"] == "Cliente A"

    def test_listar_contratos_ativos_ordena_por_nome(self, repo):
        repo.criar_contrato("B", "Cliente")
        repo.criar_contrato("A", "Cliente")

        nomes = [c["nome"] for c in repo.listar_contratos_ativos()]

        assert nomes == ["A", "B"]

    def test_listar_contratos_ativos_ignora_inativos(self, repo, db_path):
        ativo = repo.criar_contrato("Ativo", "")
        inativo = repo.criar_contrato("Inativo", "")
        with get_connection(db_path) as conn:
            conn.execute("UPDATE contratos SET ativo = 0 WHERE id = ?", (inativo,))

        ids = [c["id"] for c in repo.listar_contratos_ativos()]

        assert ativo in ids
        assert inativo not in ids

    def test_obter_primeiro_contrato_ativo_ordena_por_id(self, repo):
        primeiro = repo.criar_contrato("B", "")
        repo.criar_contrato("A", "")

        contrato = repo.obter_primeiro_contrato_ativo()

        assert contrato["id"] == primeiro

    def test_metricas_basicas_contrato(self, repo, db_path):
        cid = repo.criar_contrato("Contrato", "")
        with get_connection(db_path) as conn:
            conn.execute(
                """
                INSERT INTO documentos_previstos (contrato_id, codigo, titulo, tipo)
                VALUES (?, 'DE-15.25.00.00-6A1-1001', 'Previsto', 'DE')
                """,
                (cid,),
            )
            cur = conn.execute(
                """
                INSERT INTO documentos (contrato_id, codigo, tipo)
                VALUES (?, 'DE-15.25.00.00-6A1-1001', 'DE')
                """,
                (cid,),
            )
            doc_id = cur.lastrowid
            conn.execute(
                """
                INSERT INTO revisoes (documento_id, revisao, versao, label_revisao)
                VALUES (?, 1, 1, '1')
                """,
                (doc_id,),
            )

        metricas = repo.obter_metricas_contrato(cid)

        assert metricas == {
            "previstos": 1,
            "documentos": 1,
            "revisoes": 1,
        }

    def test_contadores_zerados_para_contrato_sem_dados(self, repo):
        cid = repo.criar_contrato("Vazio", "")

        assert repo.contar_documentos_previstos(cid) == 0
        assert repo.contar_documentos_movimentados(cid) == 0
        assert repo.contar_revisoes(cid) == 0

