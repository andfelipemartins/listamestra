"""
tests/test_services/test_contract_service.py

Testes do ContractService.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scripts"))

from init_db import init_db
from db.connection import get_connection
from core.repositories.contract_repository import ContractRepository
from core.services.contract_service import ContractService


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    init_db(path, verbose=False)
    return path


@pytest.fixture
def service(db_path):
    return ContractService(ContractRepository(db_path))


class TestContractService:

    def test_validar_dados_contrato_normaliza_strings(self, service):
        dados = service.validar_dados_contrato("  Contrato  ", "  Cliente  ")

        assert dados == {"nome": "Contrato", "cliente": "Cliente"}

    def test_validar_dados_contrato_exige_nome(self, service):
        with pytest.raises(ValueError, match="nome do contrato"):
            service.validar_dados_contrato("   ", "Cliente")

    def test_criar_contrato_normalizado(self, service):
        cid = service.criar_contrato("  Contrato A  ", "  Cliente A  ")

        contrato = service.obter_contrato_ativo(cid)
        assert contrato["nome"] == "Contrato A"
        assert contrato["cliente"] == "Cliente A"

    def test_listar_contratos_com_metricas(self, service, db_path):
        cid = service.criar_contrato("Contrato", "")
        with get_connection(db_path) as conn:
            conn.execute(
                """
                INSERT INTO documentos_previstos (contrato_id, codigo, tipo)
                VALUES (?, 'DE-15.25.00.00-6A1-1001', 'DE')
                """,
                (cid,),
            )

        contratos = service.listar_contratos_com_metricas()

        assert len(contratos) == 1
        assert contratos[0]["id"] == cid
        assert contratos[0]["previstos"] == 1
        assert contratos[0]["documentos"] == 0
        assert contratos[0]["revisoes"] == 0

    def test_obter_contrato_ativo_sem_id_retorna_primeiro_ativo(self, service):
        primeiro = service.criar_contrato("B", "")
        service.criar_contrato("A", "")

        contrato = service.obter_contrato_ativo()

        assert contrato["id"] == primeiro

    def test_listar_contratos_ativos(self, service):
        service.criar_contrato("A", "")

        contratos = service.listar_contratos_ativos()

        assert [c["nome"] for c in contratos] == ["A"]

