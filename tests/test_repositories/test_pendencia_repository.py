"""
tests/test_repositories/test_pendencia_repository.py

Testes da persistencia de dispensas de pendencias.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from core.engine.pendencias import TipoPendencia
from core.repositories.contract_repository import ContractRepository
from core.repositories.pendencia_repository import PendenciaRepository
from db.connection import get_connection
from scripts.init_db import init_db


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "pendencia-repo.db")
    init_db(path, verbose=False)
    return path


@pytest.fixture
def contrato_id(db_path):
    return ContractRepository(db_path).criar_contrato("Contrato Repository")


@pytest.fixture
def repo(db_path):
    return PendenciaRepository(db_path)


def test_schema_criado_e_indexado(db_path):
    with get_connection(db_path=db_path) as conn:
        tabela = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='pendencias_dispensas'"
        ).fetchone()
        indice = conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='index' AND name='idx_pendencias_dispensas_contrato'
            """
        ).fetchone()
    assert tabela is not None
    assert indice is not None


def test_init_db_e_idempotente(db_path):
    init_db(db_path, verbose=False)
    init_db(db_path, verbose=False)


def test_dispensar_e_listar(repo, contrato_id):
    dispensa_id = repo.dispensar(
        contrato_id,
        TipoPendencia.DOCUMENTO_SEM_TITULO,
        "DOC-001",
        "ignorada",
        "Titulo sera recebido depois",
        "editor",
    )
    rows = repo.listar_por_contrato(contrato_id)
    assert len(rows) == 1
    assert rows[0]["id"] == dispensa_id
    assert rows[0]["tipo_pendencia"] == "documento_sem_titulo"
    assert rows[0]["perfil"] == "editor"


def test_dispensar_duas_vezes_e_noop(repo, contrato_id):
    primeiro = repo.dispensar(
        contrato_id, "documento_sem_titulo", "DOC-001", "ignorada", "original"
    )
    segundo = repo.dispensar(
        contrato_id, "documento_sem_titulo", "DOC-001", "resolvida", "nova"
    )
    row = repo.buscar_por_chave(contrato_id, "documento_sem_titulo", "DOC-001")
    assert segundo == primeiro
    assert repo.contar_por_contrato(contrato_id) == 1
    assert row["acao"] == "ignorada"
    assert row["observacao"] == "original"


def test_reativar_remove_dispensa(repo, contrato_id):
    dispensa_id = repo.dispensar(
        contrato_id, "documento_sem_titulo", "DOC-001", "resolvida"
    )
    assert repo.reativar(contrato_id, dispensa_id) is True
    assert repo.listar_por_contrato(contrato_id) == []


def test_reativar_inexistente_e_noop(repo, contrato_id):
    assert repo.reativar(contrato_id, 99999) is False


def test_reativar_nao_vaza_entre_contratos(repo, db_path, contrato_id):
    outro = ContractRepository(db_path).criar_contrato("Outro Contrato")
    dispensa_id = repo.dispensar(
        contrato_id, "documento_sem_titulo", "DOC-001", "ignorada"
    )
    assert repo.reativar(outro, dispensa_id) is False
    assert repo.buscar_por_chave(
        contrato_id, "documento_sem_titulo", "DOC-001"
    ) is not None


def test_acao_invalida_e_rejeitada(repo, contrato_id):
    with pytest.raises(ValueError):
        repo.dispensar(
            contrato_id, "documento_sem_titulo", "DOC-001", "apagada"
        )
