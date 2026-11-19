from datetime import date, datetime
from pathlib import Path

import pytest
import yaml
from django.urls import reverse
from django.utils import timezone

from contas.models import Usuario
from contratos.models import Contrato, Participacao, PerfilContrato
from documentos.models import Analise, Documento, Emissao
from documentos.servicos import carregar_lista_documentos, carregar_pasta_documento


PERFIL_METRO = Path(__file__).resolve().parents[2] / "core" / "perfil" / "exemplos" / "metro.yaml"


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato de documentos",
        codigo_interno="CT-DOCS",
        cliente="Cliente de teste",
    )


@pytest.fixture
def perfil_modelo(contrato):
    with PERFIL_METRO.open(encoding="utf-8") as arquivo:
        definicao = _json_compatibility(yaml.safe_load(arquivo))
    definicao["vigencia_inicio"] = "2020-01-01"
    return PerfilContrato.objects.create(
        contrato=contrato,
        versao=1,
        vigencia_inicio=date(2020, 1, 1),
        definicao=definicao,
    )


@pytest.fixture
def usuario(contrato, django_user_model):
    pessoa = django_user_model.objects.create_user(
        username="analista", password="senha-segura", first_name="Ana", last_name="Analista"
    )
    Participacao.objects.create(
        usuario=pessoa,
        contrato=contrato,
        papel=Usuario.Perfil.EQUIPE,
        ativo=True,
    )
    return pessoa


def _json_compatibility(valor):
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {chave: _json_compatibility(item) for chave, item in valor.items()}
    if isinstance(valor, list):
        return [_json_compatibility(item) for item in valor]
    return valor


def _documento(contrato, codigo, titulo, *, atributos=None):
    valores = _valores_codigo(codigo)
    return Documento.objects.create(
        contrato=contrato,
        identificador_base=codigo,
        titulo=titulo,
        tipo=valores.get("tipo", ""),
        trecho=valores.get("trecho", ""),
        disciplina=valores.get("classe", ""),
        atributos=atributos or valores,
    )


def _valores_codigo(codigo):
    import re

    match = re.fullmatch(r"(?P<tipo>[A-Z]{2,4})-15\.(?P<trecho>\d{2})\.(?P<subtrecho>\d{2})\.(?P<unidade>\d{2})-(?P<etapa>[0-9LA])(?P<classe>[A-Z]\d)-(?P<sequencial>\d{3,4})", codigo)
    assert match, codigo
    return match.groupdict()


def _emissao(documento, revisao, data, *, fase=Emissao.Fase.PRELIMINAR, situacao=None, data_analise=None):
    emissao = Emissao.objects.create(
        documento=documento,
        revisao=revisao,
        versao=1,
        fase=fase,
        data_emissao=data,
        origem=Emissao.Origem.CLIENTE,
    )
    if situacao:
        Analise.objects.create(
            emissao=emissao,
            etapa="Análise do cliente",
            situacao=situacao,
            origem=Analise.Origem.IMPORTADO_PW,
            data_analise=data_analise,
        )
    return emissao


@pytest.mark.django_db
def test_lista_documentos_busca_e_filtra_por_caixa(client, contrato, perfil_modelo, usuario):
    escolhido = _documento(
        contrato,
        "DE-15.25.00.00-6P7-1001",
        "Terraplenagem da estação",
    )
    _documento(contrato, "PE-15.25.00.00-6A1-1002", "Procedimento de qualidade")

    dados = carregar_lista_documentos(
        usuario,
        contrato.pk,
        busca="terraplenagem",
        filtros_caixas={"classe": ["P7"]},
    )

    assert dados["total_filtrado"] == 1
    assert dados["pagina"].object_list[0]["documento"] == escolhido
    assert dados["pagina"].object_list[0]["categoria"] != "—"

    client.force_login(usuario)
    resposta = client.get(
        reverse("documentos_lista"),
        {"contrato": contrato.pk, "q": "terraplenagem", "caixa_classe": "P7"},
    )
    assert resposta.status_code == 200
    assert escolhido.identificador_base in resposta.content.decode()
    assert "Procedimento de qualidade" not in resposta.content.decode()


@pytest.mark.django_db
def test_pasta_mantem_reabertura_na_mesma_linha_e_destaca_primeira_aprovacao(
    contrato, perfil_modelo, usuario
):
    documento = _documento(contrato, "DE-15.25.00.00-6P7-1003", "Desenho aprovado e reaberto")
    _emissao(documento, "0", date(2026, 1, 1), fase=Emissao.Fase.ORIGINAL, situacao="Aprovado", data_analise=date(2026, 1, 5))
    _emissao(documento, "A1", date(2026, 2, 1), situacao="Não Conforme", data_analise=date(2026, 2, 3))
    _emissao(documento, "A", date(2026, 3, 1), fase=Emissao.Fase.ORIGINAL, situacao="Aprovado", data_analise=date(2026, 3, 5))

    pasta = carregar_pasta_documento(usuario, contrato.pk, documento.pk, hoje=date(2026, 3, 6))

    assert [item["emissao"].revisao for item in pasta["linha_tempo"]] == ["0", "A1", "A"]
    assert [item["rotulo"] for item in pasta["linha_tempo"]] == ["Emissão Inicial", "Revisão 1", "Revisão 2"]
    aprovacoes_que_contam = [
        analise
        for item in pasta["linha_tempo"]
        for analise in item["analises"]
        if analise["aprovacao_que_conta"]
    ]
    assert len(aprovacoes_que_contam) == 1
    assert aprovacoes_que_contam[0]["situacao"] == "Aprovado"


@pytest.mark.django_db
def test_pasta_mostra_prazo_da_emissao_conforme_perfil(contrato, perfil_modelo, usuario):
    documento = _documento(contrato, "DE-15.25.00.00-6P7-1004", "Desenho dentro do prazo")
    _emissao(
        documento,
        "1",
        date(2026, 1, 5),
        situacao="Aprovado",
        data_analise=date(2026, 1, 7),
    )

    pasta = carregar_pasta_documento(usuario, contrato.pk, documento.pk, hoje=date(2026, 1, 8))

    prazos = pasta["linha_tempo"][0]["prazos"]
    assert prazos
    assert any(prazo["status"].startswith("No prazo") for prazo in prazos)


@pytest.mark.django_db
def test_pasta_sem_emissao_apresenta_estado_vazio(client, contrato, perfil_modelo, usuario):
    documento = _documento(contrato, "MC-15.25.00.00-6P7-1005", "Sem emissão")
    client.force_login(usuario)

    resposta = client.get(reverse("documento_pasta", args=(contrato.pk, documento.pk)))

    assert resposta.status_code == 200
    assert "Este documento ainda não tem emissão registrada." in resposta.content.decode()
    assert resposta.context["situacao_grupo"].rotulo == "A EMITIR"


@pytest.mark.django_db
def test_documento_exige_participacao_no_contrato(client, contrato, perfil_modelo, django_user_model):
    documento = _documento(contrato, "DE-15.25.00.00-6P7-1006", "Privado ao contrato")
    externo = django_user_model.objects.create_user(username="externo", password="senha")
    client.force_login(externo)

    resposta = client.get(reverse("documento_pasta", args=(contrato.pk, documento.pk)))

    assert resposta.status_code == 403
