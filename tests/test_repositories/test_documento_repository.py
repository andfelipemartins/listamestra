"""
tests/test_repositories/test_documento_repository.py

Testes do DocumentoRepository.
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


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    init_db(path, verbose=False)
    return path


@pytest.fixture
def contrato_id(db_path):
    return ContractRepository(db_path).criar_contrato("Contrato A", "Cliente A")


@pytest.fixture
def repo(db_path):
    return DocumentoRepository(db_path)


def _criar_doc(repo, contrato_id, codigo, **kwargs):
    return repo.criar_documento(
        {
            "contrato_id": contrato_id,
            "codigo": codigo,
            "tipo": kwargs.get("tipo", "DE"),
            "titulo": kwargs.get("titulo"),
            "disciplina": kwargs.get("disciplina"),
            "modalidade": kwargs.get("modalidade"),
            "trecho": kwargs.get("trecho", "25"),
            "nome_trecho": kwargs.get("nome_trecho"),
            "responsavel": kwargs.get("responsavel"),
            "fase": kwargs.get("fase"),
            "origem": kwargs.get("origem", "teste"),
        }
    )


class TestDocumentoRepositoryEscrita:

    def test_criar_documento_retorna_id_positivo(self, repo, contrato_id):
        doc_id = _criar_doc(repo, contrato_id, "DE-15.25.00.00-6A1-1001")

        assert doc_id > 0
        doc = repo.buscar_por_id(doc_id)
        assert doc["codigo"] == "DE-15.25.00.00-6A1-1001"
        assert doc["contrato_id"] == contrato_id
        assert doc["tipo"] == "DE"
        assert doc["origem"] == "teste"

    def test_criar_documento_exige_contrato_e_codigo(self, repo):
        with pytest.raises(ValueError):
            repo.criar_documento({"codigo": "DE-15.25.00.00-6A1-1001"})

    def test_atualizar_documento_sobrescreve_campos(self, repo, contrato_id):
        doc_id = _criar_doc(repo, contrato_id, "DE-15.25.00.00-6A1-1001", titulo="Antigo")

        repo.atualizar_documento(doc_id, {"titulo": "Novo", "responsavel": "Ana"})

        doc = repo.buscar_por_id(doc_id)
        assert doc["titulo"] == "Novo"
        assert doc["responsavel"] == "Ana"

    def test_atualizar_documento_com_coalesce_preserva_null(self, repo, contrato_id):
        doc_id = _criar_doc(repo, contrato_id, "DE-15.25.00.00-6A1-1001", titulo="Original")

        repo.atualizar_documento(doc_id, {"titulo": None}, coalesce=True)

        assert repo.buscar_por_id(doc_id)["titulo"] == "Original"

    def test_atualizar_titulo_helper(self, repo, contrato_id):
        doc_id = _criar_doc(repo, contrato_id, "DE-15.25.00.00-6A1-1001")

        repo.atualizar_titulo(doc_id, "Memorial X")

        assert repo.buscar_por_id(doc_id)["titulo"] == "Memorial X"


class TestDocumentoRepositoryLeitura:

    def test_buscar_por_codigo_retorna_documento(self, repo, contrato_id):
        _criar_doc(repo, contrato_id, "DE-15.25.00.00-6A1-1001")

        doc = repo.buscar_por_codigo(contrato_id, "DE-15.25.00.00-6A1-1001")

        assert doc is not None
        assert doc["codigo"] == "DE-15.25.00.00-6A1-1001"

    def test_buscar_por_codigo_isola_por_contrato(self, repo, db_path, contrato_id):
        outro = ContractRepository(db_path).criar_contrato("Outro", "")
        _criar_doc(repo, contrato_id, "DE-15.25.00.00-6A1-1001")

        assert repo.buscar_por_codigo(outro, "DE-15.25.00.00-6A1-1001") is None

    def test_buscar_id_por_codigo(self, repo, contrato_id):
        doc_id = _criar_doc(repo, contrato_id, "DE-15.25.00.00-6A1-1001")

        assert repo.buscar_id_por_codigo(contrato_id, "DE-15.25.00.00-6A1-1001") == doc_id
        assert repo.buscar_id_por_codigo(contrato_id, "DE-99.99.99.99-9Z9-9999") is None

    def test_existe_documento(self, repo, contrato_id):
        _criar_doc(repo, contrato_id, "DE-15.25.00.00-6A1-1001")

        assert repo.existe_documento(contrato_id, "DE-15.25.00.00-6A1-1001") is True
        assert repo.existe_documento(contrato_id, "DE-99.99.99.99-9Z9-9999") is False

    def test_listar_por_contrato_ordena_por_trecho_codigo(self, repo, contrato_id):
        _criar_doc(repo, contrato_id, "DE-15.25.00.00-6A1-1002", trecho="25")
        _criar_doc(repo, contrato_id, "DE-15.19.00.00-6A1-1001", trecho="19")

        docs = repo.listar_por_contrato(contrato_id)
        codigos = [d["codigo"] for d in docs]

        assert codigos == [
            "DE-15.19.00.00-6A1-1001",
            "DE-15.25.00.00-6A1-1002",
        ]

    def test_listar_codigos_por_contrato(self, repo, contrato_id):
        _criar_doc(repo, contrato_id, "DE-15.25.00.00-6A1-1001")
        _criar_doc(repo, contrato_id, "DE-15.25.00.00-6A1-1002")

        codigos = repo.listar_codigos_por_contrato(contrato_id)

        assert codigos == [
            "DE-15.25.00.00-6A1-1001",
            "DE-15.25.00.00-6A1-1002",
        ]

    def test_listar_ids_por_contrato(self, repo, contrato_id):
        doc_a = _criar_doc(repo, contrato_id, "DE-15.25.00.00-6A1-1001")
        doc_b = _criar_doc(repo, contrato_id, "DE-15.25.00.00-6A1-1002")

        ids = repo.listar_ids_por_contrato(contrato_id)

        assert set(ids) == {doc_a, doc_b}

    def test_listar_com_ultima_revisao_inclui_documentos_sem_revisao(
        self, repo, db_path, contrato_id
    ):
        _criar_doc(repo, contrato_id, "DE-15.25.00.00-6A1-1001")

        rows = repo.listar_com_ultima_revisao(contrato_id)

        assert len(rows) == 1
        assert rows[0]["situacao"] is None
        assert rows[0]["data_emissao"] is None

    def test_listar_com_ultima_revisao_traz_dados_da_ultima(
        self, repo, db_path, contrato_id
    ):
        doc_id = _criar_doc(repo, contrato_id, "DE-15.25.00.00-6A1-1001")
        with get_connection(db_path) as conn:
            conn.execute(
                """
                INSERT INTO revisoes
                    (documento_id, revisao, versao, label_revisao,
                     data_emissao, situacao, ultima_revisao)
                VALUES (?, 0, 1, '0', '2024-01-01', 'APROVADO', 1)
                """,
                (doc_id,),
            )

        rows = repo.listar_com_ultima_revisao(contrato_id)

        assert rows[0]["situacao"] == "APROVADO"
        assert rows[0]["data_emissao"] == "2024-01-01"

    def test_listar_documentos_sem_revisao_inclui_previstos_sem_doc_e_sem_rev(
        self, repo, db_path, contrato_id
    ):
        with get_connection(db_path) as conn:
            # Previsto que nem chegou a virar documento — sem revisao
            conn.execute(
                """
                INSERT INTO documentos_previstos (contrato_id, codigo, titulo, ativo)
                VALUES (?, 'DE-15.25.00.00-6A1-1001', 'Sem doc', 1)
                """,
                (contrato_id,),
            )
            # Previsto + documento + revisao → deve ficar de fora
            conn.execute(
                """
                INSERT INTO documentos_previstos (contrato_id, codigo, titulo, ativo)
                VALUES (?, 'DE-15.25.00.00-6A1-1002', 'Com revisao', 1)
                """,
                (contrato_id,),
            )
            cur = conn.execute(
                """
                INSERT INTO documentos (contrato_id, codigo, tipo)
                VALUES (?, 'DE-15.25.00.00-6A1-1002', 'DE')
                """,
                (contrato_id,),
            )
            doc_id = cur.lastrowid
            conn.execute(
                """
                INSERT INTO revisoes (documento_id, revisao, versao, label_revisao)
                VALUES (?, 0, 1, '0')
                """,
                (doc_id,),
            )
            # Previsto + documento sem revisao
            conn.execute(
                """
                INSERT INTO documentos_previstos (contrato_id, codigo, titulo, ativo)
                VALUES (?, 'DE-15.25.00.00-6A1-1003', 'Doc sem rev', 1)
                """,
                (contrato_id,),
            )
            conn.execute(
                """
                INSERT INTO documentos (contrato_id, codigo, tipo)
                VALUES (?, 'DE-15.25.00.00-6A1-1003', 'DE')
                """,
                (contrato_id,),
            )

        sem_rev = repo.listar_documentos_sem_revisao(contrato_id)

        assert sorted(r["codigo"] for r in sem_rev) == [
            "DE-15.25.00.00-6A1-1001",
            "DE-15.25.00.00-6A1-1003",
        ]

    def test_listar_documentos_sem_revisao_ignora_inativos(
        self, repo, db_path, contrato_id
    ):
        with get_connection(db_path) as conn:
            conn.execute(
                """
                INSERT INTO documentos_previstos (contrato_id, codigo, titulo, ativo)
                VALUES (?, 'DE-15.25.00.00-6A1-1001', 'Inativo', 0)
                """,
                (contrato_id,),
            )

        assert repo.listar_documentos_sem_revisao(contrato_id) == []

    def test_buscar_documento_com_titulo_previsto_faz_fallback_para_id(
        self, repo, db_path, contrato_id
    ):
        with get_connection(db_path) as conn:
            conn.execute(
                """
                INSERT INTO documentos_previstos (contrato_id, codigo, titulo, ativo)
                VALUES (?, 'DE-15.25.00.00-6A1-1001', 'Titulo do ID', 1)
                """,
                (contrato_id,),
            )
        _criar_doc(repo, contrato_id, "DE-15.25.00.00-6A1-1001", titulo=None)

        info = repo.buscar_documento_com_titulo_previsto(
            contrato_id, "DE-15.25.00.00-6A1-1001"
        )

        assert info is not None
        assert info["titulo"] == "Titulo do ID"


class TestDocumentoRepositoryContagem:

    def test_contar_por_contrato(self, repo, contrato_id):
        _criar_doc(repo, contrato_id, "DE-15.25.00.00-6A1-1001")
        _criar_doc(repo, contrato_id, "DE-15.25.00.00-6A1-1002")

        assert repo.contar_por_contrato(contrato_id) == 2

    def test_contar_previstos_ignora_inativos(self, repo, db_path, contrato_id):
        with get_connection(db_path) as conn:
            conn.execute(
                """
                INSERT INTO documentos_previstos (contrato_id, codigo, titulo, ativo)
                VALUES (?, 'A', 'A', 1)
                """,
                (contrato_id,),
            )
            conn.execute(
                """
                INSERT INTO documentos_previstos (contrato_id, codigo, titulo, ativo)
                VALUES (?, 'B', 'B', 0)
                """,
                (contrato_id,),
            )

        assert repo.contar_previstos_por_contrato(contrato_id) == 1


class TestDocumentoRepositoryConexaoExterna:

    def test_aceita_conexao_externa_em_leitura(self, repo, db_path, contrato_id):
        _criar_doc(repo, contrato_id, "DE-15.25.00.00-6A1-1001")

        with get_connection(db_path) as conn:
            doc = repo.buscar_por_codigo(
                contrato_id, "DE-15.25.00.00-6A1-1001", conn=conn
            )

        assert doc is not None
