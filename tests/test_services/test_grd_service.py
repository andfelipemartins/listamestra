"""
tests/test_services/test_grd_service.py

Testes do GrdService â€” GRD como entidade operacional (nÃºmero Ãºnico, snapshot,
cÃ³pias, status, exportaÃ§Ã£o).
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
        assert "grd-9" in res2.mensagem.lower() or "nÃºmero" in res2.mensagem.lower()

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
        # altera a revisÃ£o depois de criada a GRD
        with get_connection(db_path) as conn:
            conn.execute("UPDATE revisoes SET situacao=?, label_revisao=? WHERE id=?",
                         ("NÃƒO APROVADO", "1", r1))
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


class TestCicloFormal:
    """TransiÃ§Ãµes unidirecionais e aÃ§Ãµes controladas."""

    def _grd(self, service, db_path, contrato_id, numero="GRD-1", status="rascunho"):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        return service.criar_grd(contrato_id, {"numero_grd": numero, "status": status}, [_item(r1, qtd_a1=4)]).grd_id

    def test_transicoes_permitidas(self, service, db_path, contrato_id):
        gid = self._grd(service, db_path, contrato_id)
        assert service.emitir_grd(gid).sucesso          # rascunho â†’ emitida
        assert service.marcar_enviada(gid).sucesso       # emitida â†’ enviada
        assert service.marcar_recebida(gid, "JoÃ£o", "Engenheiro").sucesso  # enviada â†’ recebida
        assert service.buscar_grd(gid)["status"] == "recebida"

    def test_rascunho_para_enviada_proibido(self, service, db_path, contrato_id):
        gid = self._grd(service, db_path, contrato_id)
        assert not service.marcar_enviada(gid).sucesso
        assert not service.marcar_recebida(gid, "J", "E").sucesso

    def test_recebida_imutavel(self, service, db_path, contrato_id):
        gid = self._grd(service, db_path, contrato_id)
        service.emitir_grd(gid); service.marcar_enviada(gid)
        service.marcar_recebida(gid, "JoÃ£o", "Eng")
        assert not service.marcar_enviada(gid).sucesso
        assert not service.anular_grd(gid, "x").sucesso
        # dados preservados
        assert service.listar_itens(gid)[0]["qtd_a1"] == 4

    def test_anulada_exige_motivo(self, service, db_path, contrato_id):
        gid = self._grd(service, db_path, contrato_id)
        service.emitir_grd(gid)
        assert not service.anular_grd(gid, "").sucesso
        assert not service.anular_grd(gid, "   ").sucesso
        ok = service.anular_grd(gid, "documento substituÃ­do")
        assert ok.sucesso
        grd = service.buscar_grd(gid)
        assert grd["status"] == "anulada" and grd["motivo_anulacao"] == "documento substituÃ­do"

    def test_anulada_imutavel(self, service, db_path, contrato_id):
        gid = self._grd(service, db_path, contrato_id)
        service.emitir_grd(gid)
        service.anular_grd(gid, "motivo")
        assert not service.marcar_enviada(gid).sucesso

    def test_rascunho_excluivel(self, service, db_path, contrato_id):
        gid = self._grd(service, db_path, contrato_id)
        assert service.pode_excluir(gid)
        assert service.excluir_rascunho(gid).sucesso
        assert service.buscar_grd(gid) is None

    def test_emitida_nao_excluivel(self, service, db_path, contrato_id):
        gid = self._grd(service, db_path, contrato_id)
        service.emitir_grd(gid)
        assert not service.pode_excluir(gid)
        assert not service.excluir_rascunho(gid).sucesso
        assert service.buscar_grd(gid) is not None

    def test_recebida_exige_nome_e_cargo(self, service, db_path, contrato_id):
        gid = self._grd(service, db_path, contrato_id)
        service.emitir_grd(gid); service.marcar_enviada(gid)
        assert not service.marcar_recebida(gid, "", "Eng").sucesso
        assert not service.marcar_recebida(gid, "JoÃ£o", "").sucesso

    def test_recebimento_nao_exige_email(self, service, db_path, contrato_id):
        gid = self._grd(service, db_path, contrato_id)
        service.emitir_grd(gid); service.marcar_enviada(gid)
        # sem qualquer campo de e-mail â€” deve funcionar
        res = service.marcar_recebida(gid, "JoÃ£o", "Engenheiro", declaracao="Recebi os documentos")
        assert res.sucesso
        grd = service.buscar_grd(gid)
        assert grd["recebido_por"] == "JoÃ£o" and grd["recebido_cargo"] == "Engenheiro"
        assert grd["declaracao_recebimento"] == "Recebi os documentos"


class TestNumeroFormalReservado:
    def test_numero_emitida_nao_reutilizavel(self, service, db_path, contrato_id):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        r2 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1002")
        gid = service.criar_grd(contrato_id, {"numero_grd": "GRD-7"}, [_item(r1)]).grd_id
        service.emitir_grd(gid)
        # outra GRD com mesmo nÃºmero no contrato â†’ bloqueada
        assert not service.criar_grd(contrato_id, {"numero_grd": "GRD-7"}, [_item(r2)]).sucesso

    def test_numero_anulada_nao_reutilizavel(self, service, db_path, contrato_id):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        r2 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1002")
        gid = service.criar_grd(contrato_id, {"numero_grd": "GRD-8"}, [_item(r1)]).grd_id
        service.emitir_grd(gid); service.anular_grd(gid, "erro")
        assert not service.criar_grd(contrato_id, {"numero_grd": "GRD-8"}, [_item(r2)]).sucesso

    def test_numero_rascunho_excluido_reutilizavel(self, service, db_path, contrato_id):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        r2 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1002")
        gid = service.criar_grd(contrato_id, {"numero_grd": "GRD-9"}, [_item(r1)]).grd_id
        service.excluir_rascunho(gid)
        assert service.criar_grd(contrato_id, {"numero_grd": "GRD-9"}, [_item(r2)]).sucesso


class TestToken:
    def test_gerar_e_buscar_token(self, service, db_path, contrato_id):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        gid = service.criar_grd(contrato_id, {"numero_grd": "GRD-1"}, [_item(r1)]).grd_id
        service.emitir_grd(gid)
        res = service.gerar_token_recebimento(gid)
        assert res.sucesso and len(res.mensagem) > 20
        assert service.buscar_por_token(res.mensagem)["id"] == gid

    def test_token_so_para_emitida_ou_enviada(self, service, db_path, contrato_id):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        gid = service.criar_grd(contrato_id, {"numero_grd": "GRD-1"}, [_item(r1)]).grd_id
        assert not service.gerar_token_recebimento(gid).sucesso  # rascunho

    def test_token_rejeitado_para_recebida(self, service, db_path, contrato_id):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        gid = service.criar_grd(contrato_id, {"numero_grd": "GRD-1"}, [_item(r1)]).grd_id
        service.emitir_grd(gid); service.marcar_enviada(gid)
        service.marcar_recebida(gid, "JoÃ£o", "Eng")
        assert not service.gerar_token_recebimento(gid).sucesso

    def test_token_rejeitado_para_anulada(self, service, db_path, contrato_id):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        gid = service.criar_grd(contrato_id, {"numero_grd": "GRD-1"}, [_item(r1)]).grd_id
        service.emitir_grd(gid); service.anular_grd(gid, "erro")
        assert not service.gerar_token_recebimento(gid).sucesso

    def test_renovar_token_invalida_token_anterior(self, service, db_path, contrato_id):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        gid = service.criar_grd(contrato_id, {"numero_grd": "GRD-1"}, [_item(r1)]).grd_id
        service.emitir_grd(gid)
        t1 = service.gerar_token_recebimento(gid).mensagem
        t2 = service.gerar_token_recebimento(gid).mensagem
        assert t1 != t2
        assert service.buscar_por_token(t1) is None
        assert service.buscar_por_token(t2)["id"] == gid

    def test_token_plaintext_nao_persiste_no_banco(self, service, db_path, contrato_id):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        gid = service.criar_grd(contrato_id, {"numero_grd": "GRD-1"}, [_item(r1)]).grd_id
        service.emitir_grd(gid)
        token = service.gerar_token_recebimento(gid).mensagem
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT token_recebimento, token_hash, token_expira_em FROM grd_remessas WHERE id = ?",
                (gid,),
            ).fetchone()
        assert row["token_recebimento"] is None
        assert row["token_hash"] and token not in row["token_hash"]
        assert row["token_expira_em"]

    def test_token_expirado_recusa_recebimento(self, service, db_path, contrato_id):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        gid = service.criar_grd(contrato_id, {"numero_grd": "GRD-1"}, [_item(r1)]).grd_id
        service.emitir_grd(gid); service.marcar_enviada(gid)
        token = service.gerar_token_recebimento(gid).mensagem
        with get_connection(db_path) as conn:
            conn.execute("UPDATE grd_remessas SET token_expira_em = ? WHERE id = ?", ("2000-01-01T00:00:00+00:00", gid))
        res = service.registrar_recebimento_por_token(token, "Maria", "Eng")
        assert not res.sucesso
        assert "expirou" in res.mensagem.lower()

    def test_token_uso_unico(self, service, db_path, contrato_id):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        gid = service.criar_grd(contrato_id, {"numero_grd": "GRD-1"}, [_item(r1)]).grd_id
        service.emitir_grd(gid); service.marcar_enviada(gid)
        token = service.gerar_token_recebimento(gid).mensagem
        assert service.registrar_recebimento_por_token(token, "Maria", "Eng").sucesso
        with get_connection(db_path) as conn:
            usado = conn.execute("SELECT token_usado_em FROM grd_remessas WHERE id = ?", (gid,)).fetchone()[0]
        assert usado
        res = service.registrar_recebimento_por_token(token, "Maria", "Eng")
        assert not res.sucesso
        assert "utilizado" in res.mensagem.lower() or "nao pode" in res.mensagem.lower()

    def test_token_recebimento_exige_enviada(self, service, db_path, contrato_id):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        gid = service.criar_grd(contrato_id, {"numero_grd": "GRD-1"}, [_item(r1)]).grd_id
        service.emitir_grd(gid)
        token = service.gerar_token_recebimento(gid).mensagem
        res = service.registrar_recebimento_por_token(token, "Maria", "Eng")
        assert not res.sucesso
        assert "enviada" in res.mensagem.lower()

    def test_registrar_recebimento_por_token(self, service, db_path, contrato_id):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        gid = service.criar_grd(contrato_id, {"numero_grd": "GRD-1"}, [_item(r1)]).grd_id
        service.emitir_grd(gid); service.marcar_enviada(gid)
        token = service.gerar_token_recebimento(gid).mensagem
        res = service.registrar_recebimento_por_token(token, "Maria", "Arquiteta")
        assert res.sucesso
        assert service.buscar_grd(gid)["status"] == "recebida"


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
        service.anular_grd(res.grd_id, "erro de emissÃ£o")
        assert len(service.listar_grds(contrato_id, {"status": "anulada"})) == 1
        assert len(service.listar_grds(contrato_id, {"status": "emitida"})) == 0

    def test_listar_grds_por_revisao(self, service, db_path, contrato_id):
        r1 = _doc_rev(db_path, contrato_id, "DE-15.25.00.00-6A1-1001")
        res = service.criar_grd(contrato_id, {"numero_grd": "GRD-DOC"}, [_item(r1)])
        por_rev = service.listar_grds_por_revisao([r1])
        assert r1 in por_rev
        assert por_rev[r1][0]["numero_grd"] == "GRD-DOC"

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


