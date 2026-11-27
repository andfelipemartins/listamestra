from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml
from django.urls import reverse
from django.utils import timezone

from acoes.services import carregar_minha_mesa
from contas.models import Usuario
from contratos.models import Contrato, Participacao, PerfilContrato
from documentos.models import Analise, Documento, Emissao


RAIZ = Path(__file__).resolve().parents[2]
PERFIL_METRO = RAIZ / "core" / "perfil" / "exemplos" / "metro.yaml"


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato de seções block-066",
        codigo_interno="CT-B066",
        cliente="Cliente de teste",
    )


@pytest.fixture
def perfil_modelo(contrato):
    with PERFIL_METRO.open(encoding="utf-8") as arquivo:
        definicao = yaml.safe_load(arquivo)
    definicao["vigencia_inicio"] = "2020-01-01"
    for regra in definicao["prazos"]["regras"]:
        regra.update(dias=1, tipo_dia="corridos")
    return PerfilContrato.objects.create(
        contrato=contrato,
        versao=1,
        vigencia_inicio=date(2020, 1, 1),
        definicao=definicao,
    )


@pytest.fixture
def usuario(contrato, django_user_model):
    pessoa = django_user_model.objects.create_user(
        username="equipe-block066", password="senha-segura"
    )
    Participacao.objects.create(
        usuario=pessoa,
        contrato=contrato,
        papel=Usuario.Perfil.EQUIPE,
        ativo=True,
    )
    return pessoa


def _documento(contrato, codigo, titulo):
    return Documento.objects.create(
        contrato=contrato,
        identificador_base=codigo,
        titulo=titulo,
        tipo="DE",
        atributos={"tipo": "DE"},
    )


def _emissao(documento, revisao, data_emissao, *, situacao=None, data_analise=None):
    emissao = Emissao.objects.create(
        documento=documento,
        revisao=revisao,
        versao=1,
        fase=Emissao.Fase.PRELIMINAR,
        data_emissao=data_emissao,
        origem=Emissao.Origem.CLIENTE,
    )
    if situacao is not None:
        Analise.objects.create(
            emissao=emissao,
            etapa="Análise do cliente",
            situacao=situacao,
            origem=Analise.Origem.IMPORTADO_PW,
            data_analise=data_analise,
        )
    return emissao


def _preparar_atrasos(contrato):
    hoje = timezone.localdate()
    analise = _documento(
        contrato, "DE-15.25.00.00-6A7-6001", "Título de análise atrasada"
    )
    _emissao(analise, "3", hoje - timedelta(days=11))
    revisao = _documento(
        contrato, "DE-15.25.00.00-6A7-6002", "Título de revisão atrasada"
    )
    _emissao(
        revisao,
        "2",
        hoje - timedelta(days=11),
        situacao="Não Aprovado",
        data_analise=hoje - timedelta(days=6),
    )
    return hoje, analise, revisao


@pytest.mark.django_db
def test_cards_do_inicio_apontam_para_as_secoes_de_pendencias(
    contrato, perfil_modelo, usuario, client
):
    _preparar_atrasos(contrato)
    client.force_login(usuario)

    resposta = client.get(reverse("inicio"), {"contrato": contrato.pk})
    indicadores = {item["id"]: item for item in resposta.context["indicadores_inicio"]}

    assert indicadores["atrasados"]["url"] == (
        f"{reverse('acoes:atrasados')}?contrato={contrato.pk}"
    )
    assert indicadores["atrasados"]["descricao"] == (
        "1 análise atrasada · 1 revisão atrasada"
    )
    assert indicadores["atrasados"]["ajuda"] == (
        "Análise atrasada é do cliente; revisões atrasadas são da contratada"
    )
    assert indicadores["pendencias"]["url"] == (
        f"{reverse('acoes:abertas')}?contrato={contrato.pk}"
    )


@pytest.mark.django_db
def test_secoes_de_atrasos_filtram_lado_exibem_revisao_e_trilha(
    contrato, perfil_modelo, usuario, client
):
    _, analise, revisao = _preparar_atrasos(contrato)
    client.force_login(usuario)
    atrasados = client.get(reverse("acoes:atrasados"), {"contrato": contrato.pk})
    html_atrasados = atrasados.content.decode("utf-8")

    assert f'href="{reverse("acoes:pendencias")}?contrato={contrato.pk}"' in html_atrasados
    assert f'href="{reverse("acoes:atrasados_lado", args=("analise",))}?contrato={contrato.pk}"' in html_atrasados
    assert f'href="{reverse("acoes:atrasados_lado", args=("revisoes",))}?contrato={contrato.pk}"' in html_atrasados

    url_analise = reverse("acoes:atrasados_lado", args=("analise",))
    resposta_analise = client.get(url_analise, {"contrato": contrato.pk})
    html_analise = resposta_analise.content.decode("utf-8")
    assert analise.identificador_base in html_analise
    assert "Título de análise atrasada" in html_analise
    assert "Revisão 3" in html_analise
    assert revisao.identificador_base not in html_analise
    assert f'href="{reverse("acoes:pendencias")}?contrato={contrato.pk}"' in html_analise
    assert f'href="{reverse("acoes:atrasados")}?contrato={contrato.pk}"' in html_analise
    assert f'href="{url_analise}?contrato={contrato.pk}"' in html_analise

    url_revisoes = reverse("acoes:atrasados_lado", args=("revisoes",))
    resposta_revisoes = client.get(url_revisoes, {"contrato": contrato.pk})
    html_revisoes = resposta_revisoes.content.decode("utf-8")
    assert revisao.identificador_base in html_revisoes
    assert "Título de revisão atrasada" in html_revisoes
    assert "Revisão 2" in html_revisoes
    assert analise.identificador_base not in html_revisoes
    assert f'href="{url_revisoes}?contrato={contrato.pk}"' in html_revisoes


@pytest.mark.django_db
def test_pendencias_abertas_resume_janelas_com_quantidades_ajuda_e_links(
    contrato, perfil_modelo, usuario, client
):
    _preparar_atrasos(contrato)
    client.force_login(usuario)
    mesa = carregar_minha_mesa(usuario, contrato.pk, limite=None)

    resposta = client.get(reverse("acoes:abertas"), {"contrato": contrato.pk})
    html = resposta.content.decode("utf-8")
    assert f'href="{reverse("acoes:pendencias")}?contrato={contrato.pk}"' in html
    assert f'href="{reverse("acoes:abertas")}?contrato={contrato.pk}"' in html
    for janela in mesa["janelas"]:
        quantidade = sum(item["quantidade"] for item in janela["todos"]) if janela["id"] == "recusadas" else janela["quantidade"]
        if not quantidade:
            continue
        url = f'{reverse("acoes:janela", args=(janela["id"],))}?contrato={contrato.pk}'
        assert url in html
        assert janela["titulo"] in html
        assert f"{quantidade} item" in html
    assert "documentos aguardando análise do cliente" in html
    assert "documentos aguardando nossa devolução" in html


@pytest.mark.django_db
def test_contrato_sem_participacao_nao_acessa_as_novas_secoes(
    contrato, perfil_modelo, client, django_user_model
):
    sem_acesso = django_user_model.objects.create_user(
        username="sem-contrato-block066", password="senha-segura"
    )
    client.force_login(sem_acesso)
    urls = (
        reverse("acoes:abertas"),
        reverse("acoes:atrasados"),
        reverse("acoes:atrasados_lado", args=("analise",)),
        reverse("acoes:atrasados_lado", args=("revisoes",)),
    )

    for url in urls:
        resposta = client.get(url, {"contrato": contrato.pk})
        assert resposta.status_code == 403


@pytest.mark.django_db
def test_url_antiga_de_atrasados_redireciona_para_pendencias(
    contrato, perfil_modelo, usuario, client
):
    client.force_login(usuario)

    resposta = client.get(
        reverse("acoes:atrasados_legado"), {"contrato": contrato.pk}
    )

    assert resposta.status_code == 302
    assert resposta["Location"] == (
        f"{reverse('acoes:atrasados')}?contrato={contrato.pk}"
    )
