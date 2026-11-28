from datetime import date, datetime
from pathlib import Path

import pytest
import yaml
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from contas.models import Usuario
from contratos.models import Contrato, Participacao, PerfilContrato
from documentos.models import Documento, Emissao
from documentos.servicos import carregar_pasta_documento
from grds.models import Grd, GrdItem
from grds.servicos import criar_grd, listar_grds, preparar_grd
from registro.servicos import carregar_eventos


PERFIL_METRO = Path(__file__).resolve().parents[2] / "core" / "perfil" / "exemplos" / "metro.yaml"
CODIGO_1 = "DE-15.25.00.00-6A1-1001"
CODIGO_2 = "DE-15.25.00.00-6A1-1002"
CODIGO_3 = "DE-15.25.00.00-6A1-1003"
CODIGO_CANCELADO = "DE-15.25.00.00-6A1-1004"


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato GRDs",
        codigo_interno="CT-GRD",
        cliente="Cliente GRD",
    )


@pytest.fixture
def perfil_modelo(contrato):
    with PERFIL_METRO.open(encoding="utf-8") as arquivo:
        definicao = _json_compatibility(yaml.safe_load(arquivo))
    return PerfilContrato.objects.create(
        contrato=contrato,
        versao=1,
        vigencia_inicio=date(2020, 1, 1),
        definicao=definicao,
    )


@pytest.fixture
def equipe(contrato, django_user_model):
    usuario = django_user_model.objects.create_user(
        username="equipe-b074",
        password="senha-segura",
        first_name="Ester",
        last_name="Equipe",
    )
    Participacao.objects.create(
        usuario=usuario,
        contrato=contrato,
        papel=Usuario.Perfil.EQUIPE,
        ativo=True,
    )
    return usuario


@pytest.fixture
def emissao_base(contrato, perfil_modelo):
    documento = _documento(contrato, CODIGO_1, "Planta de implantação")
    return _emissao(documento, "A", date(2026, 5, 3), versao=1)


def _json_compatibility(valor):
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {chave: _json_compatibility(item) for chave, item in valor.items()}
    if isinstance(valor, list):
        return [_json_compatibility(item) for item in valor]
    return valor


def _documento(contrato, codigo, titulo, *, cancelado_em=None):
    return Documento.objects.create(
        contrato=contrato,
        identificador_base=codigo,
        titulo=titulo,
        tipo="DE",
        trecho="25",
        disciplina="A1",
        atributos={
            "tipo": "DE",
            "linha": "15",
            "trecho": "25",
            "subtrecho": "00",
            "unidade": "00",
            "etapa": "6",
            "classe": "A1",
            "sequencial": codigo[-4:],
        },
        cancelado_em=cancelado_em,
    )


def _emissao(documento, revisao, data, *, versao=1):
    return Emissao.objects.create(
        documento=documento,
        revisao=revisao,
        versao=versao,
        fase=Emissao.Fase.ORIGINAL,
        data_emissao=data,
        origem=Emissao.Origem.INTERNA,
    )


def _grd_post_data(contrato, codigo, *, etapa="previa"):
    return {
        "contrato": contrato.pk,
        "data": "2026-11-27",
        "destinatario": "Metrô de São Paulo",
        "observacao": "Entrega para análise",
        "texto_codigos": codigo,
        "etapa": etapa,
    }


@pytest.mark.django_db
def test_previa_separa_aceitos_e_recusados_e_ignora_repetidos(contrato, perfil_modelo):
    _emissao(_documento(contrato, CODIGO_1, "Documento com emissão"), "A", date(2026, 1, 1))
    _documento(contrato, CODIGO_2, "Documento sem emissão")
    cancelado = _documento(
        contrato,
        CODIGO_CANCELADO,
        "Documento cancelado",
        cancelado_em=timezone.now(),
    )
    _emissao(cancelado, "B", date(2026, 2, 1))
    entrada = "\n".join(
        [CODIGO_1, "", CODIGO_1, CODIGO_2, CODIGO_CANCELADO, CODIGO_3]
    )

    previa = preparar_grd(contrato, entrada)

    assert [(item["codigo"], item["revisao"]) for item in previa["aceitos"]] == [(CODIGO_1, "A")]
    assert previa["recusados"] == [
        {"codigo": CODIGO_2, "motivo": "documento sem emissão"},
        {"codigo": CODIGO_CANCELADO, "motivo": "documento cancelado"},
        {"codigo": CODIGO_3, "motivo": "código não encontrado no contrato"},
    ]


@pytest.mark.django_db
def test_criacao_usa_numero_sequencial_por_contrato_e_ultima_emissao(
    contrato, perfil_modelo, equipe
):
    documento = _documento(contrato, CODIGO_1, "Documento com revisões")
    _emissao(documento, "A", date(2026, 1, 1), versao=1)
    ultima = _emissao(documento, "B", date(2026, 3, 1), versao=2)

    primeira = criar_grd(
        contrato, equipe, date(2026, 11, 27), "Destinatário", "", CODIGO_1
    )
    segunda = criar_grd(
        contrato, equipe, date(2026, 11, 28), "Destinatário", "", CODIGO_1
    )
    outro_contrato = Contrato.objects.create(
        nome="Outro contrato",
        codigo_interno="CT-OUTRO",
        cliente="Outro cliente",
    )
    PerfilContrato.objects.create(
        contrato=outro_contrato,
        versao=1,
        vigencia_inicio=date(2020, 1, 1),
        definicao=perfil_modelo.definicao,
    )
    documento_outro = _documento(outro_contrato, CODIGO_1, "Outro documento")
    _emissao(documento_outro, "A", date(2026, 1, 1))
    terceira = criar_grd(
        outro_contrato, equipe, date(2026, 11, 27), "Destinatário", "", CODIGO_1
    )

    assert primeira["grd"].numero == 1
    assert segunda["grd"].numero == 2
    assert terceira["grd"].numero == 1
    assert primeira["grd"].rotulo() == "ÁLYA 001/2026"
    assert primeira["grd"].itens.get().emissao == ultima


@pytest.mark.django_db
def test_sem_aceitos_nao_cria_grd(contrato, perfil_modelo, equipe):
    _documento(contrato, CODIGO_2, "Sem emissão")

    resultado = criar_grd(
        contrato, equipe, date(2026, 11, 27), "Destinatário", "", CODIGO_2
    )

    assert resultado["grd"] is None
    assert resultado["erro"]
    assert not Grd.objects.filter(contrato=contrato).exists()


@pytest.mark.django_db
def test_equipe_cria_pela_prevista_e_confirmacao(client, contrato, perfil_modelo, equipe, emissao_base):
    client.force_login(equipe)
    url = reverse("grds:nova")
    previa = client.post(url, _grd_post_data(contrato, CODIGO_1))

    assert previa.status_code == 200
    assert "Prévia" in previa.content.decode()
    assert CODIGO_1 in previa.content.decode()
    assert Grd.objects.count() == 0

    dados = _grd_post_data(contrato, CODIGO_1, etapa="confirmar")
    confirmacao = client.post(url, dados)

    assert confirmacao.status_code == 302
    grd = Grd.objects.get(contrato=contrato)
    assert confirmacao.url == reverse("grds:detalhe", args=(contrato.pk, grd.pk))
    assert GrdItem.objects.filter(grd=grd, emissao=emissao_base).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("papel", [Usuario.Perfil.PROJETISTA, Usuario.Perfil.CHEFIA])
def test_papeis_sem_permissao_nao_ve_botao_e_recebem_403_no_post(
    papel, client, contrato, perfil_modelo, django_user_model
):
    usuario = django_user_model.objects.create_user(username=f"restrito-{papel}", password="senha")
    Participacao.objects.create(usuario=usuario, contrato=contrato, papel=papel, ativo=True)
    client.force_login(usuario)

    lista = client.get(reverse("grds:lista"), {"contrato": contrato.pk})

    assert lista.status_code == 200
    assert "Nova GRD" not in lista.content.decode()
    assert client.post(reverse("grds:nova"), _grd_post_data(contrato, CODIGO_1)).status_code == 403


@pytest.mark.django_db
def test_nao_participante_recebe_403_na_lista_e_no_detalhe(
    client, contrato, perfil_modelo, emissao_base, equipe, django_user_model
):
    grd = criar_grd(contrato, equipe, date(2026, 11, 27), "Metrô", "", CODIGO_1)["grd"]
    externo = django_user_model.objects.create_user(username="sem-participacao", password="senha")
    client.force_login(externo)

    assert client.get(reverse("grds:lista")).status_code == 403
    assert client.get(reverse("grds:lista"), {"contrato": contrato.pk}).status_code == 403
    assert client.get(reverse("grds:detalhe", args=(contrato.pk, grd.pk))).status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("nome_url", ["grds:lista", "grds:detalhe"])
def test_anonimo_e_redirecionado_para_login(client, contrato, nome_url, equipe, emissao_base):
    grd = criar_grd(contrato, equipe, date(2026, 11, 27), "Metrô", "", CODIGO_1)["grd"]
    url = reverse(nome_url) if nome_url == "grds:lista" else reverse(nome_url, args=(contrato.pk, grd.pk))

    resposta = client.get(url)

    assert resposta.status_code == 302
    assert resposta.url.startswith(reverse("login"))
    assert f"next={url}" in resposta.url


@pytest.mark.django_db
def test_menu_pasta_e_atividade_exibem_grd(client, contrato, perfil_modelo, equipe, emissao_base):
    grd = criar_grd(
        contrato,
        equipe,
        date(2026, 11, 27),
        "Metrô de São Paulo",
        "",
        CODIGO_1,
    )["grd"]
    client.force_login(equipe)

    lista = client.get(reverse("grds:lista"), {"contrato": contrato.pk})
    pasta = client.get(reverse("documento_pasta", args=(contrato.pk, emissao_base.documento_id)))
    pasta_dados = carregar_pasta_documento(equipe, contrato.pk, emissao_base.documento_id)

    assert "GRDs" in lista.content.decode()
    assert reverse("grds:lista") in lista.content.decode()
    assert grd.rotulo() in pasta.content.decode()
    assert reverse("grds:detalhe", args=(contrato.pk, grd.pk)) in pasta.content.decode()
    assert pasta_dados["linha_tempo"][0]["grds"] == [grd]

    eventos = carregar_eventos(contrato)
    evento = next(evento for evento in eventos if evento.get("grd_id") == grd.pk)
    assert evento["acao_rotulo"] == "GRD criada"
    assert "Metrô de São Paulo" in evento["resumo"]
    assert "1 item(ns)" in evento["resumo"]
    staff = type(equipe).objects.create_user(username="staff-b074", password="senha", is_staff=True)
    client.force_login(staff)
    atividade = client.get(reverse("atividade"), {"contrato": contrato.pk})
    assert "GRD criada" in atividade.content.decode()
    assert grd.rotulo() in atividade.content.decode()


@pytest.mark.django_db
def test_lista_grds_conta_itens_sem_n_mais_um(contrato, perfil_modelo, equipe, emissao_base):
    for indice in range(8):
        Grd.objects.create(
            contrato=contrato,
            numero=indice + 1,
            data=date(2026, 1, indice + 1),
            destinatario=f"Destinatário {indice}",
            criado_por=equipe,
        )
    grd = Grd.objects.filter(contrato=contrato, numero=1).get()
    GrdItem.objects.create(grd=grd, emissao=emissao_base)

    with CaptureQueriesContext(connection) as consultas:
        grds = list(listar_grds(contrato))
        [(item.rotulo(), item.quantidade_itens, item.criado_por.username) for item in grds]

    assert len(grds) == 8
    assert len(consultas) == 1
