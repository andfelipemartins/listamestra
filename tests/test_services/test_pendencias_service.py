"""
tests/test_services/test_pendencias_service.py

Testes da orquestracao entre deteccao e dispensas.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from core.engine.pendencias import TipoPendencia
from core.repositories.contract_repository import ContractRepository
from core.repositories.documento_repository import DocumentoRepository
from core.services.pendencias_service import PendenciasService
from scripts.init_db import init_db


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "pendencias-service.db")
    init_db(path, verbose=False)
    return path


@pytest.fixture
def contrato_id(db_path):
    return ContractRepository(db_path).criar_contrato("Contrato Service")


@pytest.fixture
def service(db_path):
    return PendenciasService(db_path)


def _documento_sem_titulo(db_path, contrato_id, codigo="DOC-001", **campos):
    return DocumentoRepository(db_path).criar_documento({
        "contrato_id": contrato_id,
        "codigo": codigo,
        "titulo": campos.get("titulo"),
        "trecho": campos.get("trecho", "25"),
        "disciplina": campos.get("disciplina", "F2"),
        "tipo": "DE",
    })


def _listar_sem_titulo(service, contrato_id, **kwargs):
    return service.listar_pendencias(
        contrato_id,
        tipo=TipoPendencia.DOCUMENTO_SEM_TITULO,
        **kwargs,
    )


def test_lista_ativa_inclui_pendencia_detectada(service, db_path, contrato_id):
    _documento_sem_titulo(db_path, contrato_id)
    itens = _listar_sem_titulo(service, contrato_id)
    assert len(itens) == 1
    assert itens[0]["tipo"] == "documento_sem_titulo"
    assert itens[0]["dispensada"] is False


def test_dispensar_remove_da_lista_ativa(service, db_path, contrato_id):
    _documento_sem_titulo(db_path, contrato_id)
    service.dispensar_pendencia(
        contrato_id,
        TipoPendencia.DOCUMENTO_SEM_TITULO,
        "DOC-001",
        "ignorada",
        perfil="editor",
    )
    assert _listar_sem_titulo(service, contrato_id) == []


def test_incluir_dispensadas_exibe_metadados(service, db_path, contrato_id):
    _documento_sem_titulo(db_path, contrato_id)
    dispensa_id = service.dispensar_pendencia(
        contrato_id,
        "documento_sem_titulo",
        "DOC-001",
        "resolvida",
        observacao="Corrigido fora do sistema",
        perfil="admin",
    )
    itens = _listar_sem_titulo(
        service, contrato_id, incluir_dispensadas=True
    )
    assert len(itens) == 1
    assert itens[0]["dispensada"] is True
    assert itens[0]["dispensa_id"] == dispensa_id
    assert itens[0]["acao_dispensa"] == "resolvida"


def test_reativar_faz_pendencia_voltar(service, db_path, contrato_id):
    _documento_sem_titulo(db_path, contrato_id)
    dispensa_id = service.dispensar_pendencia(
        contrato_id, "documento_sem_titulo", "DOC-001", "ignorada"
    )
    assert service.reativar_pendencia(contrato_id, dispensa_id) is True
    assert len(_listar_sem_titulo(service, contrato_id)) == 1


def test_dispensar_duas_vezes_nao_duplica(service, db_path, contrato_id):
    _documento_sem_titulo(db_path, contrato_id)
    primeiro = service.dispensar_pendencia(
        contrato_id, "documento_sem_titulo", "DOC-001", "ignorada"
    )
    segundo = service.dispensar_pendencia(
        contrato_id, "documento_sem_titulo", "DOC-001", "resolvida"
    )
    assert segundo == primeiro
    assert len(service.listar_dispensas(contrato_id)) == 1


def test_resumo_por_categoria(service, db_path, contrato_id):
    _documento_sem_titulo(db_path, contrato_id, "DOC-001")
    _documento_sem_titulo(db_path, contrato_id, "DOC-002")
    resumo = service.resumo_por_categoria(contrato_id)
    assert resumo["documento_sem_titulo"] == 2
    assert set(resumo) == {tipo.value for tipo in TipoPendencia}


def test_isolamento_por_contrato(service, db_path, contrato_id):
    outro = ContractRepository(db_path).criar_contrato("Outro")
    _documento_sem_titulo(db_path, contrato_id, "DOC-IGUAL")
    _documento_sem_titulo(db_path, outro, "DOC-IGUAL")
    service.dispensar_pendencia(
        contrato_id, "documento_sem_titulo", "DOC-IGUAL", "ignorada"
    )
    assert _listar_sem_titulo(service, contrato_id) == []
    assert len(_listar_sem_titulo(service, outro)) == 1


def test_filtros_de_trecho_e_disciplina(service, db_path, contrato_id):
    _documento_sem_titulo(
        db_path, contrato_id, "DOC-F2", trecho="25", disciplina="F2"
    )
    _documento_sem_titulo(
        db_path, contrato_id, "DOC-J2", trecho="23", disciplina="J2"
    )
    itens = service.listar_pendencias(
        contrato_id,
        tipo="documento_sem_titulo",
        trecho="25",
        disciplina="F2",
    )
    assert [item["codigo"] for item in itens] == ["DOC-F2"]


@pytest.mark.parametrize(
    "tipo,chave,acao",
    [
        ("nao_existe", "DOC-001", "ignorada"),
        ("documento_sem_titulo", "DOC-001", "apagada"),
        ("documento_sem_titulo", "  ", "ignorada"),
    ],
)
def test_dispensa_invalida_e_rejeitada(
    service, contrato_id, tipo, chave, acao
):
    with pytest.raises(ValueError):
        service.dispensar_pendencia(contrato_id, tipo, chave, acao)
