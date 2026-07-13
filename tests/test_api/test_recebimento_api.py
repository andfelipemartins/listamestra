# PURPOSE: Valida o fluxo HTTP publico de recebimento de GRD por token.
# INPUTS: SQLite temporario, GrdService e FastAPI TestClient.
# OUTPUTS: Cobertura de GET/POST valido, recusas e preservacao de dados UTF-8.
# DEPS: pytest, fastapi.testclient, services e repositories de GRD existentes.
# SEE: api/main.py, core/services/grd_service.py

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scripts"))

from api.main import create_app
from core.repositories.contract_repository import ContractRepository
from core.repositories.documento_repository import DocumentoRepository
from core.repositories.revisao_repository import RevisaoRepository
from core.services.grd_service import GrdService
from db.connection import get_connection
from init_db import init_db


@pytest.fixture
def recebimento(db_path):
    contrato_id = ContractRepository(db_path).criar_contrato("Contrato API", "Cliente API")
    documento_id = DocumentoRepository(db_path).criar_documento({
        "contrato_id": contrato_id,
        "codigo": "DE-15.25.00.00-6A1-1001",
        "tipo": "DE",
        "titulo": "Projeto de teste da GRD",
        "trecho": "25",
        "disciplina": "A1",
        "origem": "teste_api",
    })
    revisao_id = RevisaoRepository(db_path).criar_revisao({
        "documento_id": documento_id,
        "revisao": 0,
        "versao": 1,
        "label_revisao": "0",
        "data_emissao": "2026-07-10",
        "situacao": "APROVADO",
        "ultima_revisao": 1,
        "origem": "teste_api",
    })
    service = GrdService(db_path=db_path)
    criada = service.criar_grd(
        contrato_id,
        {
            "numero_grd": "GRD-API-001",
            "status": "emitida",
            "data_envio": "2026-07-11",
            "destinatario": "Producao",
            "obra": "Obra de teste",
        },
        [{"revisao_id": revisao_id, "qtd_digital": 1}],
    )
    assert criada.sucesso
    assert service.marcar_enviada(criada.grd_id).sucesso
    token = service.gerar_token_recebimento(criada.grd_id).dados["token"]
    client = TestClient(create_app(lambda: GrdService(db_path=db_path)))
    return {"client": client, "service": service, "grd_id": criada.grd_id, "token": token}


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "api.db")
    init_db(path, verbose=False)
    return path


def _url(token: str) -> str:
    return f"/grd/receber/{token}"


def test_rota_de_diagnostico_responde_sem_banco(db_path):
    client = TestClient(create_app(lambda: GrdService(db_path=db_path)))
    resposta = client.get("/")
    assert resposta.status_code == 200
    assert resposta.text == "SCLME - servico de recebimento de GRD"


def test_get_token_valido_exibe_resumo_e_itens(recebimento):
    resposta = recebimento["client"].get(_url(recebimento["token"]))
    assert resposta.status_code == 200
    assert "GRD-API-001" in resposta.text
    assert "DE-15.25.00.00-6A1-1001" in resposta.text
    assert "Projeto de teste da GRD" in resposta.text
    assert "Obra de teste" in resposta.text
    assert "Producao" in resposta.text


def test_get_token_invalido_nao_vaza_dados_da_grd(recebimento):
    resposta = recebimento["client"].get(_url("token-invalido"))
    assert resposta.status_code == 400
    assert "Token invalido" in resposta.text
    assert "GRD-API-001" not in resposta.text
    assert "DE-15.25.00.00-6A1-1001" not in resposta.text


def test_get_token_expirado_exibe_erro(recebimento, db_path):
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE grd_remessas SET token_expira_em = ? WHERE id = ?",
            ("2000-01-01T00:00:00+00:00", recebimento["grd_id"]),
        )
    resposta = recebimento["client"].get(_url(recebimento["token"]))
    assert resposta.status_code == 400
    assert "expirou" in resposta.text.lower()
    assert "GRD-API-001" not in resposta.text


def test_post_valido_confirma_recebimento_e_persiste_dados(recebimento):
    resposta = recebimento["client"].post(
        _url(recebimento["token"]),
        data={
            "recebido_por": "João da Silva",
            "recebido_cargo": "Coordenação",
            "recebido_em": "2026-07-12",
            "declaracao": "Recebi os documentos relacionados acima.",
        },
    )
    assert resposta.status_code == 200
    assert "Recebimento confirmado" in resposta.text
    grd = recebimento["service"].buscar_grd(recebimento["grd_id"])
    assert grd["status"] == "recebida"
    assert grd["recebido_por"] == "João da Silva"
    assert grd["recebido_cargo"] == "Coordenação"
    assert grd["recebido_em"] == "2026-07-12"


@pytest.mark.parametrize("campo", ["recebido_por", "recebido_cargo"])
def test_post_sem_campo_obrigatorio_reexibe_formulario(recebimento, campo):
    dados = {
        "recebido_por": "Maria",
        "recebido_cargo": "Engenheira",
        "recebido_em": "2026-07-12",
        "declaracao": "Teste",
    }
    dados[campo] = ""
    resposta = recebimento["client"].post(_url(recebimento["token"]), data=dados)
    assert resposta.status_code == 400
    assert "obrigatorios" in resposta.text.lower()
    assert recebimento["service"].buscar_grd(recebimento["grd_id"])["status"] == "enviada"


def test_post_duplo_recusa_segunda_confirmacao(recebimento):
    dados = {"recebido_por": "Maria", "recebido_cargo": "Engenheira", "recebido_em": "2026-07-12"}
    primeira = recebimento["client"].post(_url(recebimento["token"]), data=dados)
    segunda = recebimento["client"].post(_url(recebimento["token"]), data=dados)
    assert primeira.status_code == 200
    assert segunda.status_code == 400
    assert "utilizado" in segunda.text.lower()
    assert "GRD-API-001" not in segunda.text


def test_get_token_ja_utilizado_exibe_erro_sem_dados(recebimento):
    dados = {"recebido_por": "Maria", "recebido_cargo": "Engenheira", "recebido_em": "2026-07-12"}
    recebimento["client"].post(_url(recebimento["token"]), data=dados)
    resposta = recebimento["client"].get(_url(recebimento["token"]))
    assert resposta.status_code == 400
    assert "utilizado" in resposta.text.lower()
    assert "GRD-API-001" not in resposta.text


def test_grd_anulada_apos_token_recusa_get_e_post(recebimento):
    assert recebimento["service"].anular_grd(recebimento["grd_id"], "Teste de anulacao").sucesso
    get_resposta = recebimento["client"].get(_url(recebimento["token"]))
    post_resposta = recebimento["client"].post(
        _url(recebimento["token"]),
        data={"recebido_por": "Maria", "recebido_cargo": "Engenheira"},
    )
    assert get_resposta.status_code == 400
    assert post_resposta.status_code == 400
    assert "GRD-API-001" not in get_resposta.text
    assert "GRD-API-001" not in post_resposta.text


def test_post_data_invalida_reexibe_formulario(recebimento):
    resposta = recebimento["client"].post(
        _url(recebimento["token"]),
        data={"recebido_por": "Maria", "recebido_cargo": "Engenheira", "recebido_em": "data-errada"},
    )
    assert resposta.status_code == 400
    assert "data valida" in resposta.text.lower()
    assert recebimento["service"].buscar_grd(recebimento["grd_id"])["status"] == "enviada"


def test_formulario_escapa_valores_do_destinatario(recebimento):
    resposta = recebimento["client"].post(
        _url(recebimento["token"]),
        data={
            "recebido_por": "<script>alert('x')</script>",
            "recebido_cargo": "",
            "recebido_em": "2026-07-12",
        },
    )
    assert resposta.status_code == 400
    assert "&lt;script&gt;" in resposta.text
    assert "<script>" not in resposta.text
