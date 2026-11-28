import pytest
from django.urls import reverse

from contas.models import Usuario
from contratos.models import Contrato, Participacao


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato do Painel",
        codigo_interno="CT-PAINEL",
        cliente="Cliente de teste",
    )


@pytest.fixture
def participante(contrato, django_user_model):
    usuario = django_user_model.objects.create_user(
        username="participante-painel",
        password="senha-segura",
    )
    Participacao.objects.create(
        usuario=usuario,
        contrato=contrato,
        papel=Usuario.Perfil.CHEFIA,
        ativo=True,
    )
    return usuario


@pytest.mark.django_db
def test_url_legada_do_resumo_redireciona_para_o_painel(client, contrato):
    resposta = client.get(reverse("resumo_executivo", args=(contrato.pk,)))

    assert resposta.status_code == 301
    assert resposta["Location"] == reverse("painel", args=(contrato.pk,))


@pytest.mark.django_db
def test_painel_nao_mostra_resumo_executivo_e_mostra_imprimir(
    client, contrato, participante, monkeypatch
):
    from painel import views

    client.force_login(participante)
    monkeypatch.setattr(
        views,
        "_contexto_painel",
        lambda contrato, *args, **kwargs: {
            "contrato": contrato,
            "total_documentos_previstos": 0,
            "total_documentos_id": 0,
            "pode_ver_fotos": False,
            "pode_guardar_foto": False,
            "grupo_cards": [],
            "percentual_avanco": 0,
            "fora_do_painel": [],
            "fora_do_id": 0,
            "quantidade_filtros_ativos": 0,
            "filtros_ativos": False,
            "filtros": [],
            "caixas": [],
            "categorias": [],
            "recortes": [],
            "indicadores_prazo": [],
            "indicador_cronograma": None,
            "estados_nao_mapeados": [],
            "ultima_situacao_pw": None,
            "ultima_importacao_id": None,
            "grafico_pizza": {},
        },
    )

    resposta = client.get(reverse("painel", args=(contrato.pk,)))

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Resumo executivo" not in html
    assert "Imprimir" in html
    assert "@media print" in html
    assert "print-color-adjust: exact" in html
    assert "beforeprint" in html
    assert "window.print()" in html
