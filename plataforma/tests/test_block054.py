from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import resolve, reverse

from contratos.models import Contrato, Participacao


def _menu(usuario):
    request = RequestFactory().get(reverse("inicio"))
    request.resolver_match = resolve(request.path)
    return render_to_string(
        "base.html",
        {"request": request, "user": usuario, "contratos_painel": []},
    )


@pytest.mark.django_db
def test_atividade_e_menu_restritos_a_admin_do_contrato(client, django_user_model):
    contrato = Contrato.objects.create(
        nome="Contrato de atividade",
        codigo_interno="CT-ATIVIDADE",
        cliente="Cliente de teste",
    )
    equipe = django_user_model.objects.create_user(username="equipe-atividade", password="senha")
    Participacao.objects.create(
        usuario=equipe,
        contrato=contrato,
        papel=django_user_model.Perfil.EQUIPE,
    )

    client.force_login(equipe)
    assert client.get(reverse("atividade"), {"contrato": contrato.pk}).status_code == 403
    assert f'href="{reverse("atividade")}"' not in _menu(equipe)

    administrador = django_user_model.objects.create_user(
        username="admin-atividade", password="senha"
    )
    Participacao.objects.create(
        usuario=administrador,
        contrato=contrato,
        papel=django_user_model.Perfil.ADMIN,
    )
    outro_contrato = Contrato.objects.create(
        nome="Outro contrato de atividade",
        codigo_interno="CT-ATIVIDADE-2",
        cliente="Cliente de teste",
    )
    Participacao.objects.create(
        usuario=administrador,
        contrato=outro_contrato,
        papel=django_user_model.Perfil.ADMIN,
    )
    client.force_login(administrador)
    resposta = client.get(reverse("atividade"), {"contrato": contrato.pk})

    assert resposta.status_code == 200
    html = resposta.content.decode()
    assert html.count(f'href="{reverse("atividade")}"') == 1
    for campo in ("contrato", "pessoa", "acao", "de", "ate", "codigo"):
        assert f'<label for="atividade-{campo}">' in html
        assert f'id="atividade-{campo}"' in html


def test_titulo_longo_do_painel_renderiza_com_limite_e_nome_completo_no_title():
    nome = "Contrato " + "X" * 120
    html = render_to_string(
        "painel/_conteudo.html",
        {
            "contrato": SimpleNamespace(
                pk=1,
                nome=nome,
                codigo_interno="CT-LONGO",
                cliente="Cliente de teste",
            ),
            "grupo_cards": (),
            "filtros": (),
            "caixas": (),
            "indicadores_aprovacao": (),
            "recortes": (),
            "grafico_pizza": {},
            "user": AnonymousUser(),
        },
    )

    assert f'class="painel-titulo-contrato" title="{nome}"' in html
    assert f"<h1 class=\"painel-titulo-contrato\" title=\"{nome}\">{nome}</h1>" in html
