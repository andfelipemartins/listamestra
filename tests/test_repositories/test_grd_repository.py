"""
tests/test_repositories/test_grd_repository.py

Testes do GrdRepository — agregado GRD em lote (grd_remessas + grd_itens).
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
from core.repositories.grd_repository import GrdRepository


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
    return GrdRepository(db_path)


def _doc_com_revisao(db_path, contrato_id, codigo, label="0", ultima=1, **rev):
    doc_repo = DocumentoRepository(db_path)
    rev_repo = RevisaoRepository(db_path)
    doc_id = doc_repo.criar_documento({
        "contrato_id": contrato_id, "codigo": codigo, "tipo": "DE", "origem": "teste",
    })
    try:
        revisao_int = int(label)
    except (ValueError, TypeError):
        revisao_int = None
    rev_id = rev_repo.criar_revisao({
        "documento_id": doc_id, "revisao": revisao_int, "versao": rev.get("versao", 1),
        "label_revisao": label, "data_emissao": rev.get("data_emissao", "2025-01-01"),
        "situacao": rev.get("situacao", "APROVADO"),
        "ultima_revisao": ultima, "origem": "teste",
    })
    return doc_id, rev_id


class TestCriarRemessa:
    def test_criar_remessa_retorna_id(self, repo, contrato_id):
        grd_id = repo.criar_remessa({
            "contrato_id": contrato_id, "numero_grd": "GRD-001",
            "data_envio": "2026-06-07", "setor": "Produção",
        })
        assert isinstance(grd_id, int) and grd_id > 0

    def test_criar_remessa_exige_contrato(self, repo):
        with pytest.raises(ValueError):
            repo.criar_remessa({"numero_grd": "X"})

    def test_remessa_aparece_em_listar(self, repo, contrato_id):
        repo.criar_remessa({"contrato_id": contrato_id, "numero_grd": "GRD-009"})
        remessas = repo.listar_remessas(contrato_id)
        assert len(remessas) == 1
        assert remessas[0]["numero_grd"] == "GRD-009"
        assert remessas[0]["total_itens"] == 0


class TestVincularItens:
    def test_adicionar_multiplas_revisoes(self, repo, db_path, contrato_id):
        _, r1 = _doc_com_revisao(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        _, r2 = _doc_com_revisao(db_path, contrato_id, "DE-15.25.00.00-6A1-1002")
        _, r3 = _doc_com_revisao(db_path, contrato_id, "DE-15.25.00.00-6A1-1003")

        grd_id = repo.criar_remessa({"contrato_id": contrato_id, "numero_grd": "GRD-100"})
        inseridos = repo.adicionar_itens(grd_id, [r1, r2, r3])

        assert inseridos == 3
        itens = repo.listar_itens(grd_id)
        assert len(itens) == 3
        assert {it["revisao_id"] for it in itens} == {r1, r2, r3}

    def test_total_itens_reflete_vinculos(self, repo, db_path, contrato_id):
        _, r1 = _doc_com_revisao(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        _, r2 = _doc_com_revisao(db_path, contrato_id, "DE-15.25.00.00-6A1-1002")
        grd_id = repo.criar_remessa({"contrato_id": contrato_id})
        repo.adicionar_itens(grd_id, [r1, r2])
        assert repo.listar_remessas(contrato_id)[0]["total_itens"] == 2

    def test_vinculo_duplicado_eh_idempotente(self, repo, db_path, contrato_id):
        _, r1 = _doc_com_revisao(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        grd_id = repo.criar_remessa({"contrato_id": contrato_id})
        repo.adicionar_item(grd_id, r1)
        repo.adicionar_item(grd_id, r1)  # mesma chave — ignorada
        assert len(repo.listar_itens(grd_id)) == 1

    def test_itens_trazem_dados_do_documento(self, repo, db_path, contrato_id):
        _, r1 = _doc_com_revisao(db_path, contrato_id, "DE-15.25.00.00-6A1-1001", label="0")
        grd_id = repo.criar_remessa({"contrato_id": contrato_id})
        repo.adicionar_item(grd_id, r1)
        it = repo.listar_itens(grd_id)[0]
        assert it["codigo"] == "DE-15.25.00.00-6A1-1001"
        assert it["label_revisao"] == "0"


class TestDocumentosParaGrd:
    def test_lista_apenas_documentos_com_revisao(self, repo, db_path, contrato_id):
        _doc_com_revisao(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        # documento sem revisão não deve aparecer
        DocumentoRepository(db_path).criar_documento({
            "contrato_id": contrato_id, "codigo": "DE-15.25.00.00-6A1-9999",
            "tipo": "DE", "origem": "teste",
        })
        docs = repo.listar_documentos_para_grd(contrato_id)
        codigos = {d["codigo"] for d in docs}
        assert "DE-15.25.00.00-6A1-1001" in codigos
        assert "DE-15.25.00.00-6A1-9999" not in codigos

    def test_documento_traz_revisao_id(self, repo, db_path, contrato_id):
        _, r1 = _doc_com_revisao(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        doc = repo.listar_documentos_para_grd(contrato_id)[0]
        assert doc["revisao_id"] == r1


class TestNumeroEStatus:
    def test_numero_existe(self, repo, contrato_id):
        repo.criar_remessa({"contrato_id": contrato_id, "numero_grd": "GRD-1"})
        assert repo.numero_existe(contrato_id, "GRD-1")
        assert not repo.numero_existe(contrato_id, "GRD-2")

    def test_numero_existe_ignora_excluido(self, repo, contrato_id):
        gid = repo.criar_remessa({"contrato_id": contrato_id, "numero_grd": "GRD-1"})
        assert not repo.numero_existe(contrato_id, "GRD-1", excluir_id=gid)

    def test_status_default_rascunho(self, repo, contrato_id):
        gid = repo.criar_remessa({"contrato_id": contrato_id, "numero_grd": "GRD-1"})
        assert repo.buscar_por_id(gid)["status"] == "rascunho"

    def test_atualizar_status(self, repo, contrato_id):
        gid = repo.criar_remessa({"contrato_id": contrato_id, "numero_grd": "GRD-1"})
        repo.atualizar_status(gid, "emitida")
        assert repo.buscar_por_id(gid)["status"] == "emitida"

    def test_atualizar_status_invalido(self, repo, contrato_id):
        gid = repo.criar_remessa({"contrato_id": contrato_id})
        with pytest.raises(ValueError):
            repo.atualizar_status(gid, "xpto")

    def test_buscar_por_numero(self, repo, contrato_id):
        repo.criar_remessa({"contrato_id": contrato_id, "numero_grd": "GRD-ABC"})
        assert repo.buscar_por_numero(contrato_id, "GRD-ABC")["numero_grd"] == "GRD-ABC"


class TestSnapshotItem:
    def test_adicionar_item_snapshot(self, repo, db_path, contrato_id):
        _, r1 = _doc_com_revisao(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        gid = repo.criar_remessa({"contrato_id": contrato_id, "numero_grd": "GRD-1"})
        repo.adicionar_item_snapshot(gid, {
            "revisao_id": r1, "codigo_snapshot": "DE-15.25.00.00-6A1-1001",
            "titulo_snapshot": "Planta", "label_revisao_snapshot": "0",
            "versao_snapshot": 1, "situacao_snapshot": "APROVADO",
            "qtd_a1": 2, "qtd_digital": 5,
        })
        it = repo.listar_itens(gid)[0]
        assert it["codigo"] == "DE-15.25.00.00-6A1-1001"
        assert it["situacao"] == "APROVADO"
        assert it["qtd_a1"] == 2 and it["qtd_digital"] == 5

    def test_listar_remessas_filtro_status(self, repo, contrato_id):
        g1 = repo.criar_remessa({"contrato_id": contrato_id, "numero_grd": "GRD-1"})
        repo.atualizar_status(g1, "cancelada")
        repo.criar_remessa({"contrato_id": contrato_id, "numero_grd": "GRD-2"})
        assert len(repo.listar_remessas(contrato_id, {"status": "cancelada"})) == 1
        assert len(repo.listar_remessas(contrato_id, {"status": "rascunho"})) == 1

    def test_listar_remessas_filtro_numero(self, repo, contrato_id):
        repo.criar_remessa({"contrato_id": contrato_id, "numero_grd": "GRD-ABC"})
        repo.criar_remessa({"contrato_id": contrato_id, "numero_grd": "GRD-XYZ"})
        assert len(repo.listar_remessas(contrato_id, {"numero": "ABC"})) == 1
