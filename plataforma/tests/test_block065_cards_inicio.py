from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml
from django.urls import reverse
from django.utils import timezone

from acoes.services import carregar_resumo_inicio
from contas.models import Usuario
from contratos.models import Contrato, Participacao, PerfilContrato
from documentos.models import Analise, Documento, Emissao


RAIZ = Path(__file__).resolve().parents[2]
PERFIL_METRO = RAIZ / "core" / "perfil" / "exemplos" / "metro.yaml"


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato dos cards D-101",
        codigo_interno="CT-B065",
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
        username="equipe-block065", password="senha-segura"
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


def _emissao(documento, data_emissao, *, situacao=None, data_analise=None):
    emissao = Emissao.objects.create(
        documento=documento,
        revisao="1",
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


def _preparar_documentos(contrato):
    hoje = timezone.localdate()
    cliente_mais_atrasado = _documento(
        contrato, "DE-15.25.00.00-6A7-1001", "Cliente mais atrasado"
    )
    _emissao(cliente_mais_atrasado, hoje - timedelta(days=11))
    cliente_atrasado = _documento(
        contrato, "DE-15.25.00.00-6A7-1002", "Cliente atrasado"
    )
    _emissao(cliente_atrasado, hoje - timedelta(days=6))
    nosso_atrasado = _documento(
        contrato, "DE-15.25.00.00-6A7-1003", "Nossa devolução atrasada"
    )
    _emissao(
        nosso_atrasado,
        hoje - timedelta(days=11),
        situacao="Não Aprovado",
        data_analise=hoje - timedelta(days=6),
    )
    em_dia = _documento(contrato, "DE-15.25.00.00-6A7-1004", "Ainda no prazo")
    _emissao(em_dia, hoje)
    return hoje, cliente_mais_atrasado, cliente_atrasado, nosso_atrasado, em_dia


@pytest.mark.django_db
def test_card_atrasados_mostra_divisao_e_abre_sua_lista(
    contrato, perfil_modelo, usuario, client
):
    _preparar_documentos(contrato)
    client.force_login(usuario)

    resposta = client.get(reverse("inicio"), {"contrato": contrato.pk})
    html = resposta.content.decode("utf-8")
    card = next(
        indicador
        for indicador in resposta.context["indicadores_inicio"]
        if indicador["id"] == "atrasados"
    )

    assert card["descricao"] == "2 do cliente · 1 nossos"
    assert card["url"] == f"{reverse('acoes:atrasados')}?contrato={contrato.pk}"
    for indicador in resposta.context["indicadores_inicio"]:
        assert indicador["ajuda"]
        assert f'title="{indicador["ajuda"]}"' in html
        assert indicador["ajuda"] in html
    assert f'href="{card["url"]}"' in html


@pytest.mark.django_db
def test_visao_atrasados_separa_janelas_exclui_em_dia_e_ordena(
    contrato, perfil_modelo, usuario, client
):
    hoje, cliente_mais_atrasado, cliente_atrasado, nosso_atrasado, em_dia = _preparar_documentos(contrato)
    client.force_login(usuario)

    resposta = client.get(reverse("acoes:atrasados"), {"contrato": contrato.pk})
    html = resposta.content.decode("utf-8")
    cliente_index = html.index("Atraso do cliente")
    nosso_index = html.index("Atraso nosso")

    assert resposta.status_code == 200
    assert cliente_index < html.index(cliente_mais_atrasado.identificador_base) < html.index(cliente_atrasado.identificador_base)
    assert html.index(nosso_atrasado.identificador_base) > nosso_index
    assert em_dia.identificador_base not in html
    assert "Atrasado há 10 dias" in html
    assert "Moderado" in html
    assert reverse("documento_pasta", args=(contrato.pk, cliente_mais_atrasado.pk)) in html
    assert "Voltar ao Início" in html


@pytest.mark.django_db
def test_visao_atrasados_respeita_acesso_ao_contrato(
    contrato, perfil_modelo, client, django_user_model
):
    sem_acesso = django_user_model.objects.create_user(
        username="sem-contrato-block065", password="senha-segura"
    )
    client.force_login(sem_acesso)

    resposta = client.get(reverse("acoes:atrasados"), {"contrato": contrato.pk})

    assert resposta.status_code == 403
