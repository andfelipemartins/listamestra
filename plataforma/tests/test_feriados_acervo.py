from dataclasses import replace
from datetime import date
import json
from pathlib import Path

import pytest
import yaml
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.urls import reverse

from contratos.admin import FeriadoAcervoAdmin
from contratos.models import Contrato, FeriadoAcervo, PerfilContrato
from core.perfil import carregar_yaml
from core.perfil.feriados import FeriadoExtra, feriados_nacionais
from painel.prazos import feriados_prazo


RAIZ_REPOSITORIO = Path(__file__).resolve().parents[2]
PERFIL_METRO = RAIZ_REPOSITORIO / "core" / "perfil" / "exemplos" / "metro.yaml"


def _definicao_perfil_metro():
    dados = yaml.safe_load(PERFIL_METRO.read_text(encoding="utf-8"))
    return json.loads(json.dumps(dados, default=lambda valor: valor.isoformat()))


@pytest.mark.django_db
def test_migracao_carrega_feriados_de_sao_paulo():
    aniversario = FeriadoAcervo.objects.get(nome="Aniversário de São Paulo")
    revolucao = FeriadoAcervo.objects.get(nome="Revolução Constitucionalista")
    corpus_christi = FeriadoAcervo.objects.get(nome="Corpus Christi")

    assert (aniversario.abrangencia, aniversario.uf, aniversario.municipio) == (
        "municipal",
        "SP",
        "São Paulo",
    )
    assert (aniversario.tipo_regra, aniversario.dia, aniversario.mes) == ("fixa", 25, 1)
    assert (revolucao.abrangencia, revolucao.uf, revolucao.dia, revolucao.mes) == (
        "estadual",
        "SP",
        9,
        7,
    )
    assert (corpus_christi.abrangencia, corpus_christi.deslocamento_pascoa) == (
        "municipal",
        60,
    )


@pytest.mark.django_db
def test_calendario_do_perfil_metro_monta_feriados_regionais():
    perfil = carregar_yaml(PERFIL_METRO)

    datas = feriados_prazo(perfil.prazos, [], date(2026, 1, 1))

    assert date(2026, 1, 25) in datas
    assert date(2026, 6, 4) in datas
    assert date(2026, 7, 9) in datas


def test_perfil_sem_regiao_monta_somente_nacionais_e_extras():
    perfil = carregar_yaml(PERFIL_METRO)
    feriados = replace(
        perfil.prazos.feriados,
        regiao=None,
        extras=(FeriadoExtra(date(2026, 6, 5), "Extra do perfil"),),
    )
    prazos = replace(perfil.prazos, feriados=feriados)

    datas = feriados_prazo(prazos, [], date(2026, 1, 1))

    assert datas == set(feriados_nacionais(2026)) | {date(2026, 6, 5)}
    assert date(2026, 1, 25) not in datas
    assert date(2026, 6, 4) not in datas
    assert date(2026, 7, 9) not in datas


@pytest.mark.django_db
def test_alteracoes_do_acervo_ficam_no_historico():
    feriado = FeriadoAcervo.objects.get(nome="Revolução Constitucionalista")
    feriado.nome = "Revolução Constitucionalista de 1932"
    feriado.save()

    assert feriado.history.count() == 1
    assert feriado.history.first().nome == "Revolução Constitucionalista de 1932"


@pytest.mark.django_db
def test_modelo_recusa_municipal_sem_municipio():
    feriado = FeriadoAcervo(
        nome="Feriado sem cidade",
        abrangencia=FeriadoAcervo.Abrangencia.MUNICIPAL,
        uf="SP",
        tipo_regra=FeriadoAcervo.TipoRegra.FIXA,
        dia=1,
        mes=1,
    )

    with pytest.raises(ValidationError) as erro:
        feriado.full_clean()

    assert "municipio" in erro.value.message_dict


@pytest.mark.django_db
def test_admin_lista_o_acervo_para_usuario_staff(client, django_user_model):
    staff = django_user_model.objects.create_user(
        username="staff-feriados",
        password="senha-segura",
        is_staff=True,
    )
    client.force_login(staff)

    resposta = client.get(reverse("admin:contratos_feriadoacervo_changelist"))

    assert resposta.status_code == 200
    assert "Corpus Christi" in resposta.content.decode()
    model_admin = admin.site._registry[FeriadoAcervo]
    assert isinstance(model_admin, FeriadoAcervoAdmin)


@pytest.mark.django_db
def test_tela_feriados_identifica_origem_do_acervo_com_uf(client, django_user_model):
    contrato = Contrato.objects.create(
        nome="Contrato de teste",
        codigo_interno="CT-FERIADOS",
        cliente="Cliente de teste",
    )
    definicao = _definicao_perfil_metro()
    perfil = PerfilContrato.objects.create(
        contrato=contrato,
        versao=1,
        vigencia_inicio=date.fromisoformat(definicao["vigencia_inicio"]),
        definicao=definicao,
    )
    administrador = django_user_model.objects.create_superuser(
        username="admin-feriados-acervo",
        email="admin-feriados-acervo@example.com",
        password="senha-segura",
    )
    client.force_login(administrador)

    resposta = client.get(
        reverse("admin:contratos_perfilcontrato_feriados", args=(perfil.pk,))
    )

    assert resposta.status_code == 200
    assert any(
        item["nome"] == "Corpus Christi" and item["origem"] == "Acervo (SP)"
        for item in resposta.context["itens"]
    )
