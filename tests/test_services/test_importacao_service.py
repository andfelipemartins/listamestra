"""
tests/test_services/test_importacao_service.py

Testes do ImportacaoService.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scripts"))

from init_db import init_db
from core.repositories.contract_repository import ContractRepository
from core.repositories.importacao_repository import ImportacaoRepository
from core.services.importacao_service import ImportacaoService


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    init_db(path, verbose=False)
    return path


@pytest.fixture
def contrato_id(db_path):
    return ContractRepository(db_path).criar_contrato("Contrato", "Cliente")


@pytest.fixture
def service(db_path):
    return ImportacaoService(ImportacaoRepository(db_path))


class TestImportacaoService:

    def test_validar_dados_importacao_normaliza_campos(self, service, contrato_id):
        dados = service.validar_dados_importacao(
            contrato_id=contrato_id,
            origem="  lista_documentos  ",
            arquivo_importado="  lista.xlsx  ",
            total_registros="10",
            status="  em_andamento  ",
            usuario="  andre  ",
        )

        assert dados == {
            "contrato_id": contrato_id,
            "origem": "lista_documentos",
            "arquivo_importado": "lista.xlsx",
            "total_registros": 10,
            "status": "em_andamento",
            "usuario": "andre",
        }

    def test_validar_dados_importacao_exige_contrato(self, service):
        with pytest.raises(ValueError, match="contrato"):
            service.validar_dados_importacao(0, "lista", "a.xlsx", 1)

    def test_validar_dados_importacao_exige_origem(self, service, contrato_id):
        with pytest.raises(ValueError, match="origem"):
            service.validar_dados_importacao(contrato_id, " ", "a.xlsx", 1)

    def test_validar_dados_importacao_rejeita_total_negativo(self, service, contrato_id):
        with pytest.raises(ValueError, match="negativo"):
            service.validar_dados_importacao(contrato_id, "lista", "a.xlsx", -1)

    def test_registrar_importacao_normalizada(self, service, contrato_id):
        imp_id = service.registrar_importacao(
            contrato_id=contrato_id,
            origem=" lista ",
            arquivo_importado=" arquivo.xlsx ",
            total_registros="3",
        )

        historico = service.listar_historico_importacoes(contrato_id)
        assert historico[0]["arquivo_importado"] == "arquivo.xlsx"
        assert historico[0]["total_registros"] == 3
        assert imp_id > 0

    def test_obter_ultima_importacao(self, service, contrato_id):
        imp_id = service.registrar_importacao(contrato_id, "lista", "lista.xlsx", 2)
        service.finalizar_importacao(
            importacao_id=imp_id,
            total_erros=0,
            total_novos=2,
            total_atualizados=0,
        )

        ultima = service.obter_ultima_importacao(contrato_id)

        assert ultima["arquivo_importado"] == "lista.xlsx"
        assert ultima["total_novos"] == 2

    def test_obter_resumo_importacoes(self, service, contrato_id):
        imp_id = service.registrar_importacao(contrato_id, "lista", "lista.xlsx", 2)
        service.finalizar_importacao(imp_id, total_erros=0, total_novos=1, total_atualizados=1)

        resumo = service.obter_resumo_importacoes(contrato_id)

        assert resumo["total"] == 1
        assert resumo["ultima"]["arquivo_importado"] == "lista.xlsx"
        assert len(resumo["historico"]) == 1
