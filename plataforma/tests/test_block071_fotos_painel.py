from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml
from django.urls import reverse
from django.utils import timezone

from contas.models import Usuario
from contratos.models import Contrato, Participacao, PerfilContrato
from painel.models import FotoPainel
from painel.servicos import CAMPOS_FOTO_PAINEL, guardar_foto, listar_fotos
from registro.servicos import carregar_eventos


PERFIL_METRO = Path(__file__).resolve().parents[2] / "core" / "perfil" / "exemplos" / "metro.yaml"
HOJE = date(2026, 11, 27)


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato do block-071",
        codigo_interno="CT-B071",
        cliente="Cliente de teste",
    )


@pytest.fixture
def perfil_modelo(contrato):
    with PERFIL_METRO.open(encoding="utf-8") as arquivo:
        definicao = yaml.safe_load(arquivo)
    inicio = timezone.localdate() - timedelta(days=30)
    definicao["vigencia_inicio"] = inicio.isoformat()
    return PerfilContrato.objects.create(
        contrato=contrato,
        versao=1,
        vigencia_inicio=inicio,
        definicao=definicao,
    )


@pytest.fixture
def participante(contrato, django_user_model):
    usuario = django_user_model.objects.create_user(
        username="participante-b071",
        password="senha-segura",
        first_name="Paula",
    )
    Participacao.objects.create(
        usuario=usuario,
        contrato=contrato,
        papel=Usuario.Perfil.EQUIPE,
        ativo=True,
    )
    return usuario


@pytest.fixture
def admin_contrato(contrato, django_user_model):
    usuario = django_user_model.objects.create_user(
        username="admin-b071",
        password="senha-segura",
        first_name="Ana",
    )
    Participacao.objects.create(
        usuario=usuario,
        contrato=contrato,
        papel=Usuario.Perfil.ADMIN,
        ativo=True,
    )
    return usuario


def _numeros(**alteracoes):
    numeros = {campo: 0 for campo, _ in CAMPOS_FOTO_PAINEL}
    numeros.update(alteracoes)
    return numeros


@pytest.mark.django_db
def test_guardar_foto_persiste_os_numeros_do_resumo_executivo(
    contrato, perfil_modelo, participante
):
    from painel.servicos import carregar_resumo_executivo

    resumo = carregar_resumo_executivo(contrato, participante, hoje=HOJE)
    esperado = {campo: resumo[campo] for campo, _ in CAMPOS_FOTO_PAINEL}

    foto = guardar_foto(contrato, participante, hoje=HOJE)

    assert foto.data == HOJE
    assert foto.criado_por == participante
    assert foto.numeros == esperado


@pytest.mark.django_db
def test_guardar_de_novo_no_mesmo_dia_substitui_a_foto(
    contrato, participante, monkeypatch
):
    import painel.servicos as servicos

    resumo = {campo: 1 for campo, _ in CAMPOS_FOTO_PAINEL}
    monkeypatch.setattr(servicos, "carregar_resumo_executivo", lambda *args, **kwargs: resumo)
    guardar_foto(contrato, participante, hoje=HOJE)

    resumo["previstos"] = 4
    foto = guardar_foto(contrato, participante, hoje=HOJE)

    assert FotoPainel.objects.filter(contrato=contrato, data=HOJE).count() == 1
    assert foto.numeros["previstos"] == 4
    assert FotoPainel.history.filter(contrato_id=contrato.pk).count() == 2


@pytest.mark.django_db
def test_listar_fotos_calcula_diferenca_para_a_foto_anterior(contrato, participante):
    FotoPainel.objects.create(
        contrato=contrato,
        data=HOJE - timedelta(days=1),
        numeros=_numeros(avanco_percentual=10.0, previstos=8, emitidos=3),
        criado_por=participante,
    )
    FotoPainel.objects.create(
        contrato=contrato,
        data=HOJE,
        numeros=_numeros(avanco_percentual=12.5, previstos=7, emitidos=6),
        criado_por=participante,
    )

    fotos = listar_fotos(contrato)

    assert [item["foto"].data for item in fotos] == [HOJE, HOJE - timedelta(days=1)]
    assert fotos[0]["diferencas"]["avanco_percentual"] == 2.5
    assert fotos[0]["diferencas"]["previstos"] == -1
    assert fotos[0]["diferencas"]["emitidos"] == 3
    assert all(valor is None for valor in fotos[1]["diferencas"].values())


@pytest.mark.django_db
def test_usuario_sem_permissao_recebe_403_no_post(
    client, contrato, perfil_modelo, participante
):
    client.force_login(participante)
    client.raise_request_exception = False

    resposta = client.post(reverse("painel_guardar_foto", args=(contrato.pk,)))

    assert resposta.status_code == 403
    assert not FotoPainel.objects.filter(contrato=contrato).exists()


@pytest.mark.django_db
def test_usuario_sem_participacao_nao_acessa_a_pagina_de_fotos(
    client, contrato, perfil_modelo, django_user_model
):
    externo = django_user_model.objects.create_user(username="externo-b071", password="senha")
    client.force_login(externo)

    resposta = client.get(reverse("painel_fotos", args=(contrato.pk,)))

    assert resposta.status_code == 403


@pytest.mark.django_db
def test_foto_aparece_na_atividade_com_rotulo_e_autor(
    contrato, perfil_modelo, admin_contrato
):
    guardar_foto(contrato, admin_contrato, hoje=HOJE)

    evento = next(
        item
        for item in carregar_eventos(contrato)
        if item["acao_rotulo"] == "Foto do Painel guardada"
    )

    assert evento["usuario_nome"] == "Ana"
    assert "27/11/2026" in evento["resumo"]
    assert {item["campo"] for item in evento["detalhes"]} >= {"Data", "Previstos"}


@pytest.mark.django_db
def test_post_redireciona_para_fotos_com_mensagem(
    client, contrato, perfil_modelo, admin_contrato
):
    client.force_login(admin_contrato)

    resposta = client.post(
        reverse("painel_guardar_foto", args=(contrato.pk,)),
        follow=True,
    )

    assert resposta.status_code == 200
    assert resposta.redirect_chain[-1][0] == reverse("painel_fotos", args=(contrato.pk,))
    assert "Foto de hoje guardada." in resposta.content.decode()


@pytest.mark.django_db
def test_botao_para_guardar_foto_aparece_somente_para_staff_ou_admin(
    client, contrato, perfil_modelo, participante, admin_contrato
):
    client.force_login(participante)
    resposta_participante = client.get(reverse("painel", args=(contrato.pk,)))
    assert resposta_participante.status_code == 200
    assert "Guardar foto de hoje" not in resposta_participante.content.decode()

    client.force_login(admin_contrato)
    resposta_admin = client.get(reverse("painel", args=(contrato.pk,)))
    html_admin = resposta_admin.content.decode()
    assert resposta_admin.status_code == 200
    assert "Guardar foto de hoje" in html_admin
    assert reverse("painel_fotos", args=(contrato.pk,)) in html_admin
