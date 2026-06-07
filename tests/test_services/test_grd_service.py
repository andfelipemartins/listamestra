"""
tests/test_services/test_grd_service.py

Testes do GrdService — GRD como entidade operacional (número único, snapshot,
cópias, status, exportação).
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
        "titulo": rev.get("titulo", "Documento"), "trecho": rev.get("trecho", "25"),
        "disciplina": rev.get("disciplina", "A1"), "origem": "teste",
    })
    rev_id = RevisaoRepository(db_path).criar_revisao({
        "documento_id": doc_id, "revisao": 0, "versao": 1, "label_revisao": "0",
        "data_emissao": rev.get("data_emissao", "2025-01-01"),
        "situacao": rev.get("situacao", "APROVADO"),
        "ultima_revisao": 1, "origem": "teste",
    })
    return rev_id


def _item(rid, **qtd):
    return {"revisao_id": rid, **qtd}


class TestCriarGrd:
    def test_uma_grd_para_multiplos_documentos(self, service, db_path, contrato_id):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        r2 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1002")
        r3 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1003")
        res = service.criar_grd(
            contrato_id, {"numero_grd": "GRD-001", "status": "emitida"},
            [_item(r1), _item(r2), _item(r3)],
        )
        assert res.sucesso and res.total_itens == 3
        grds = service.listar_grds(contrato_id)
        assert len(grds) == 1 and grds[0]["total_itens"] == 3

    def test_sem_selecao_falha(self, service, contrato_id):
        res = service.criar_grd(contrato_id, {"numero_grd": "GRD-001"}, [])
        assert not res.sucesso

    def test_status_inicial_padrao_rascunho(self, service, db_path, contrato_id):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        res = service.criar_grd(contrato_id, {}, [_item(r1)])
        assert res.sucesso
        assert service.buscar_grd(res.grd_id)["status"] == "rascunho"

    def test_status_inicial_emitida(self, service, db_path, contrato_id):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        res = service.criar_grd(contrato_id, {"status": "emitida"}, [_item(r1)])
        assert service.buscar_grd(res.grd_id)["status"] == "emitida"


class TestNumeroUnico:
    def test_numero_duplicado_no_contrato_bloqueia(self, service, db_path, contrato_id):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        r2 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1002")
        assert service.criar_grd(contrato_id, {"numero_grd": "GRD-9"}, [_item(r1)]).sucesso
        res2 = service.criar_grd(contrato_id, {"numero_grd": "GRD-9"}, [_item(r2)])
        assert not res2.sucesso
        assert "grd-9" in res2.mensagem.lower() or "número" in res2.mensagem.lower()

    def test_mesmo_numero_em_contratos_diferentes_permitido(self, service, db_path):
        c1 = ContractRepository(db_path).criar_contrato("C1", "X")
        c2 = ContractRepository(db_path).criar_contrato("C2", "Y")
        r1 = _doc_rev(db_path, c1, "DE-15.25.00.00-6A1-1001")
        r2 = _doc_rev(db_path, c2, "DE-15.25.00.00-6A1-1002")
        assert service.criar_grd(c1, {"numero_grd": "GRD-1"}, [_item(r1)]).sucesso
        assert service.criar_grd(c2, {"numero_grd": "GRD-1"}, [_item(r2)]).sucesso


class TestSnapshotECopias:
    def test_snapshot_congela_situacao(self, service, db_path, contrato_id):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001", situacao="APROVADO")
        res = service.criar_grd(contrato_id, {"numero_grd": "GRD-1"}, [_item(r1)])
        # altera a revisão depois de criada a GRD
        with get_connection(db_path) as conn:
            conn.execute("UPDATE revisoes SET situacao=?, label_revisao=? WHERE id=?",
                         ("NÃO APROVADO", "1", r1))
        it = service.listar_itens(res.grd_id)[0]
        assert it["situacao"] == "APROVADO"      # congelado
        assert it["label_revisao"] == "0"         # congelado

    def test_snapshot_guarda_codigo_e_titulo(self, service, db_path, contrato_id):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001", titulo="Planta Geral")
        res = service.criar_grd(contrato_id, {"numero_grd": "GRD-1"}, [_item(r1)])
        it = service.listar_itens(res.grd_id)[0]
        assert it["codigo"] == "DE-15.25.00.00-6A1-1001"
        assert it["titulo"] == "Planta Geral"

    def test_copias_por_formato(self, service, db_path, contrato_id):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        res = service.criar_grd(
            contrato_id, {"numero_grd": "GRD-1"},
            [_item(r1, qtd_a0=1, qtd_a1=2, qtd_a4=5, qtd_digital=3)],
        )
        it = service.listar_itens(res.grd_id)[0]
        assert (it["qtd_a0"], it["qtd_a1"], it["qtd_a4"], it["qtd_digital"]) == (1, 2, 5, 3)
        assert it["qtd_a2"] == 0 and it["qtd_a3"] == 0


class TestStatus:
    def test_alterar_status(self, service, db_path, contrato_id):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        res = service.criar_grd(contrato_id, {"numero_grd": "GRD-1"}, [_item(r1)])
        service.alterar_status(res.grd_id, "enviada")
        assert service.buscar_grd(res.grd_id)["status"] == "enviada"

    def test_status_invalido_falha(self, service, db_path, contrato_id):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        res = service.criar_grd(contrato_id, {"numero_grd": "GRD-1"}, [_item(r1)])
        assert not service.alterar_status(res.grd_id, "xpto").sucesso

    def test_cancelar_preserva_dados(self, service, db_path, contrato_id):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        res = service.criar_grd(contrato_id, {"numero_grd": "GRD-1"}, [_item(r1, qtd_a1=4)])
        service.cancelar_grd(res.grd_id)
        grd = service.buscar_grd(res.grd_id)
        assert grd["status"] == "cancelada"
        # itens e cópias preservados
        it = service.listar_itens(res.grd_id)[0]
        assert it["qtd_a1"] == 4


class TestBuscaEExportData:
    def test_busca_por_numero(self, service, db_path, contrato_id):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        service.criar_grd(contrato_id, {"numero_grd": "GRD-ABC"}, [_item(r1)])
        achados = service.listar_grds(contrato_id, {"numero": "ABC"})
        assert len(achados) == 1 and achados[0]["numero_grd"] == "GRD-ABC"

    def test_busca_por_documento(self, service, db_path, contrato_id):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-7777")
        r2 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-8888")
        service.criar_grd(contrato_id, {"numero_grd": "GRD-1"}, [_item(r1)])
        service.criar_grd(contrato_id, {"numero_grd": "GRD-2"}, [_item(r2)])
        achados = service.listar_grds(contrato_id, {"codigo": "7777"})
        assert len(achados) == 1 and achados[0]["numero_grd"] == "GRD-1"

    def test_filtro_por_status(self, service, db_path, contrato_id):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        res = service.criar_grd(contrato_id, {"numero_grd": "GRD-1", "status": "emitida"}, [_item(r1)])
        service.cancelar_grd(res.grd_id)
        assert len(service.listar_grds(contrato_id, {"status": "cancelada"})) == 1
        assert len(service.listar_grds(contrato_id, {"status": "emitida"})) == 0

    def test_montar_dados_exportacao(self, service, db_path, contrato_id):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        res = service.criar_grd(contrato_id, {"numero_grd": "GRD-1"}, [_item(r1)])
        dados = service.montar_dados_exportacao(res.grd_id)
        assert dados["cabecalho"]["numero_grd"] == "GRD-1"
        assert len(dados["itens"]) == 1


class TestListarSelecionaveis:
    def test_lista_enriquecida_com_revisao_id(self, service, db_path, contrato_id):
        _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        docs = service.listar_documentos_selecionaveis(contrato_id)
        assert len(docs) == 1
        assert "revisao_id" in docs[0] and docs[0]["nome_trecho"] == "Ragueb Chohfi"

    def test_documento_sem_revisao_nao_aparece(self, service, db_path, contrato_id):
        DocumentoRepository(db_path).criar_documento({
            "contrato_id": contrato_id, "codigo": "DE-15.25.00.00-6A1-9999",
            "tipo": "DE", "origem": "teste",
        })
        assert service.listar_documentos_selecionaveis(contrato_id) == []
