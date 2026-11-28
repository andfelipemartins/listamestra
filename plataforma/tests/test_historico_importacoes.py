from datetime import date, datetime

import pytest
from django.utils import timezone
from django.urls import reverse

from contas.models import Usuario
from contratos.models import Contrato, Participacao
from importacoes.models import (
    ImportacaoCronograma,
    ImportacaoID,
    ImportacaoSituacao,
    IndiceDocumentos,
)
from tests.importacoes_helpers import ativar_contrato


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato principal",
        codigo_interno="CT-HIST",
        cliente="Cliente de teste",
    )


@pytest.fixture
def outro_contrato(db):
    return Contrato.objects.create(
        nome="Outro contrato",
        codigo_interno="CT-OUTRO",
        cliente="Outro cliente",
    )


@pytest.fixture
def participante(contrato, django_user_model):
    usuario = django_user_model.objects.create_user(
        username="ana-historico",
        password="senha",
        first_name="Ana",
        last_name="Silva",
    )
    Participacao.objects.create(
        usuario=usuario,
        contrato=contrato,
        papel=Usuario.Perfil.EQUIPE,
        ativo=True,
    )
    return usuario


def _momento(dia, hora):
    return timezone.make_aware(datetime(2026, 1, dia, hora, 30))


def _importacao_id(contrato, usuario, arquivo, momento, validas=0, invalidas=0):
    indice = IndiceDocumentos.objects.create(
        contrato=contrato,
        codigo=f"ID-{arquivo}",
        revisao="1",
        fonte=IndiceDocumentos.Fonte.EXCEL_ID,
        arquivo_nome=arquivo,
        importado_em=momento,
    )
    importacao = ImportacaoID.objects.create(
        contrato=contrato,
        indice=indice,
        arquivo_nome=arquivo,
        importado_por=usuario,
        linhas_validas=validas,
        linhas_invalidas=invalidas,
    )
    ImportacaoID.objects.filter(pk=importacao.pk).update(importado_em=momento)
    return importacao


def _importacao_situacao(contrato, usuario, arquivo, momento, **contadores):
    importacao = ImportacaoSituacao.objects.create(
        contrato=contrato,
        data_extracao=date(2026, 1, 10),
        arquivo_nome=arquivo,
        importado_por=usuario,
        **contadores,
    )
    ImportacaoSituacao.objects.filter(pk=importacao.pk).update(importado_em=momento)
    return importacao


def _importacao_cronograma(contrato, usuario, arquivo, momento, validas=0, recusadas=0):
    importacao = ImportacaoCronograma.objects.create(
        contrato=contrato,
        arquivo_nome=arquivo,
        importado_por=usuario,
        linhas_validas=validas,
        linhas_recusadas=recusadas,
    )
    ImportacaoCronograma.objects.filter(pk=importacao.pk).update(importado_em=momento)
    return importacao


def test_lista_importacoes_do_contrato_em_ordem_e_distingue_situacoes(
    client, contrato, outro_contrato, participante
):
    client.force_login(participante)
    ativar_contrato(client, contrato)
    momento_id = _momento(1, 9)
    momento_pw = _momento(2, 10)
    momento_planilha = _momento(3, 11)
    momento_cronograma = _momento(4, 12)
    _importacao_id(contrato, participante, "id.xlsx", momento_id, validas=312, invalidas=4)
    _importacao_situacao(
        contrato,
        participante,
        "extracao.xlsx",
        momento_pw,
        documentos=30,
        emissoes=42,
        fora_do_id=2,
        linhas_invalidas=3,
    )
    _importacao_situacao(
        contrato,
        participante,
        "[Planilha padrão] situacao.xlsx",
        momento_planilha,
        documentos=25,
        emissoes=5,
        linhas_invalidas=1,
    )
    _importacao_cronograma(
        contrato, participante, "cronograma.xlsx", momento_cronograma, validas=18, recusadas=2
    )
    _importacao_cronograma(
        outro_contrato,
        participante,
        "outro-contrato.xlsx",
        _momento(5, 13),
        validas=99,
    )

    resposta = client.get(reverse("historico_importacoes", args=(contrato.pk,)))

    assert resposta.status_code == 200
    linhas = resposta.context["importacoes"]
    assert [(linha["tipo"], linha["arquivo"]) for linha in linhas] == [
        ("Cronograma", "cronograma.xlsx"),
        ("Situação por planilha", "situacao.xlsx"),
        ("Situação do PW", "extracao.xlsx"),
        ("ID", "id.xlsx"),
    ]
    assert linhas[0]["data_hora"] == "04/01/2026 12:30"
    assert "312 válidas · 4 recusadas" in linhas[3]["resumo"]
    assert "30 documentos · 42 emissões · 2 fora do ID · 3 inválidas" in linhas[2]["resumo"]
    assert linhas[3]["importado_por"] == "Ana Silva"
    conteudo = resposta.content.decode()
    assert "Histórico de importações" in conteudo
    assert "Situação por planilha" in conteudo
    assert "outro-contrato.xlsx" not in conteudo


def test_participante_de_outro_contrato_recebe_403(client, outro_contrato, django_user_model, contrato):
    usuario = django_user_model.objects.create_user(username="participante-alheio", password="senha")
    Participacao.objects.create(
        usuario=usuario,
        contrato=outro_contrato,
        papel=Usuario.Perfil.EQUIPE,
        ativo=True,
    )
    client.force_login(usuario)
    ativar_contrato(client, contrato)

    resposta = client.get(reverse("historico_importacoes", args=(contrato.pk,)))

    assert resposta.status_code == 403


def test_anonimo_e_redirecionado_para_login(client, contrato):
    resposta = client.get(reverse("historico_importacoes", args=(contrato.pk,)))

    assert resposta.status_code == 302
    assert resposta.url.startswith("/contas/login/?next=")


def test_staff_acessa_historico(client, contrato, django_user_model):
    staff = django_user_model.objects.create_user(
        username="staff-historico",
        password="senha",
        is_staff=True,
    )
    client.force_login(staff)
    ativar_contrato(client, contrato)

    resposta = client.get(reverse("historico_importacoes", args=(contrato.pk,)))

    assert resposta.status_code == 200


def test_link_de_recusadas_so_aparece_quando_importacao_tem_linhas_recusadas(
    client, contrato, participante
):
    client.force_login(participante)
    ativar_contrato(client, contrato)
    _importacao_id(contrato, participante, "id-sem-recusa.xlsx", _momento(1, 9), validas=4)
    _importacao_situacao(
        contrato,
        participante,
        "pw-sem-recusa.xlsx",
        _momento(2, 9),
        documentos=4,
    )
    resposta_sem_recusas = client.get(reverse("historico_importacoes", args=(contrato.pk,)))
    assert not any(linha["tem_recusadas"] for linha in resposta_sem_recusas.context["importacoes"])
    assert f'href="{reverse("linhas_recusadas", args=(contrato.pk,))}"' not in (
        resposta_sem_recusas.content.decode()
    )

    _importacao_cronograma(
        contrato, participante, "cronograma-com-recusa.xlsx", _momento(3, 9), recusadas=1
    )
    resposta_com_recusas = client.get(reverse("historico_importacoes", args=(contrato.pk,)))

    assert resposta_com_recusas.content.decode().count(
        f'href="{reverse("linhas_recusadas", args=(contrato.pk,))}"'
    ) == 1


def test_contrato_sem_importacoes_mostra_mensagem_vazia_e_acentos(
    client, contrato, participante
):
    client.force_login(participante)
    ativar_contrato(client, contrato)

    resposta = client.get(reverse("historico_importacoes", args=(contrato.pk,)))

    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "Nenhuma importação neste contrato ainda." in conteudo
    assert "Histórico de importações" in conteudo
    assert "importações" in conteudo


def test_historico_e_somente_get(client, contrato, participante):
    client.force_login(participante)
    ativar_contrato(client, contrato)

    resposta = client.post(reverse("historico_importacoes", args=(contrato.pk,)))

    assert resposta.status_code == 405
