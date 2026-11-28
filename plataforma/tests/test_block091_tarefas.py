from datetime import date, timedelta

import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from contas.models import Usuario
from contratos.models import Contrato, Participacao
from documentos.models import Documento, Emissao
from tarefas.models import Equipe, Tarefa
from tarefas.servicos import (
    carregar_resumo_tarefas,
    concluir_tarefa,
    criar_tarefa,
    pode_atribuir,
    tarefas_da_equipe,
)


def _usuario(django_user_model, nome, **kwargs):
    return django_user_model.objects.create_user(username=nome, password="senha", **kwargs)


def _contrato(codigo):
    return Contrato.objects.create(codigo_interno=codigo, nome=codigo, cliente="Metrô")


def _participar(usuario, contrato, papel=Usuario.Perfil.EQUIPE):
    return Participacao.objects.create(
        usuario=usuario, contrato=contrato, papel=papel, ativo=True
    )


def _equipe(contrato, gestor, nome, *membros, equipe_mae=None):
    equipe = Equipe.objects.create(
        contrato=contrato, nome=nome, gestor=gestor, equipe_mae=equipe_mae
    )
    equipe.membros.add(*membros)
    return equipe


def _tarefa(contrato, responsavel, criada_por, *, documento=None, prazo=None):
    return criar_tarefa(
        contrato=contrato,
        usuario=criada_por,
        titulo="Revisar documento",
        descricao="",
        responsavel=responsavel,
        prazo=prazo or date.today() + timedelta(days=1),
        documento=documento,
    )


@pytest.mark.django_db
def test_gestor_atribui_a_membro_da_equipe_mas_nao_a_pessoa_de_fora(django_user_model):
    contrato = _contrato("CT-091-A")
    gestor = _usuario(django_user_model, "gestor-091")
    membro = _usuario(django_user_model, "membro-091")
    externo = _usuario(django_user_model, "externo-091")
    for pessoa in (gestor, membro, externo):
        _participar(pessoa, contrato)
    _equipe(contrato, gestor, "Projetos", membro)

    assert pode_atribuir(gestor, membro, contrato)
    assert not pode_atribuir(gestor, externo, contrato)
    tarefa = _tarefa(contrato, membro, gestor)
    assert tarefa.responsavel == membro
    with pytest.raises(PermissionDenied):
        _tarefa(contrato, externo, gestor)


@pytest.mark.django_db
def test_membro_cria_tarefa_para_si_e_admin_atribui_a_qualquer_participante(django_user_model):
    contrato = _contrato("CT-091-B")
    membro = _usuario(django_user_model, "membro-091-b")
    admin = _usuario(django_user_model, "admin-091-b")
    participante = _usuario(django_user_model, "participante-091-b")
    _participar(membro, contrato)
    _participar(admin, contrato, Usuario.Perfil.ADMIN)
    _participar(participante, contrato)

    propria = _tarefa(contrato, membro, membro)
    atribuida = _tarefa(contrato, participante, admin)

    assert propria.responsavel == membro
    assert atribuida.criada_por == admin
    assert atribuida.responsavel == participante


@pytest.mark.django_db
def test_gestor_com_equipes_em_dois_contratos_consulta_somente_o_contrato_ativo(django_user_model):
    gestor = _usuario(django_user_model, "gestor-091-duplo")
    primeiro, segundo = _contrato("CT-091-C1"), _contrato("CT-091-C2")
    membro_a = _usuario(django_user_model, "membro-091-c1")
    membro_b = _usuario(django_user_model, "membro-091-c2")
    for contrato, membro in ((primeiro, membro_a), (segundo, membro_b)):
        _participar(gestor, contrato)
        _participar(membro, contrato)
        _equipe(contrato, gestor, f"Equipe {contrato.codigo_interno}", membro)
        _tarefa(contrato, membro, gestor)

    assert list(tarefas_da_equipe(gestor, primeiro).values_list("contrato_id", flat=True)) == [primeiro.pk]
    assert list(tarefas_da_equipe(gestor, segundo).values_list("contrato_id", flat=True)) == [segundo.pk]


@pytest.mark.django_db
def test_emissao_nova_sugere_feita_sem_concluir_e_so_responsavel_conclui(django_user_model):
    contrato = _contrato("CT-091-D")
    gestor = _usuario(django_user_model, "gestor-091-d")
    responsavel = _usuario(django_user_model, "responsavel-091-d")
    _participar(gestor, contrato)
    _participar(responsavel, contrato)
    _equipe(contrato, gestor, "Equipe D", responsavel)
    documento = Documento.objects.create(
        contrato=contrato,
        identificador_base="DE-15.25.00.00-6A1-1001",
        titulo="Desenho",
    )
    tarefa = _tarefa(contrato, responsavel, gestor, documento=documento)
    criado = tarefa.history.order_by("-history_id").first()
    assert criado.history_change_reason == "Tarefa criada"
    Emissao.objects.create(
        documento=documento,
        revisao="1",
        fase=Emissao.Fase.ORIGINAL,
        data_emissao=date.today(),
        origem=Emissao.Origem.INTERNA,
    )
    tarefa.refresh_from_db()

    assert tarefa.parece_feita
    assert tarefa.status == Tarefa.Status.ABERTA
    with pytest.raises(PermissionDenied):
        concluir_tarefa(tarefa=tarefa, usuario=gestor)
    concluida = concluir_tarefa(tarefa=tarefa, usuario=responsavel)
    assert concluida.status == Tarefa.Status.CONCLUIDA
    assert concluida.concluida_em is not None
    assert concluida.history.order_by("-history_id").first().history_change_reason == "Tarefa concluída"


@pytest.mark.django_db
def test_card_inicio_mostra_tarefas_pessoais_e_resumo_da_equipe(client, django_user_model):
    gestor = _usuario(django_user_model, "gestor-091-home")
    membro = _usuario(django_user_model, "membro-091-home")
    contrato = _contrato("CT-091-HOME")
    _participar(gestor, contrato)
    _participar(membro, contrato)
    _equipe(contrato, gestor, "Equipe Home", membro)
    minha = _tarefa(contrato, gestor, gestor, prazo=date.today() - timedelta(days=1))
    _tarefa(contrato, membro, gestor, prazo=date.today() - timedelta(days=2))
    client.force_login(gestor)
    sessao = client.session
    sessao["contrato_ativo_id"] = contrato.pk
    sessao.save()

    resposta = client.get(reverse("inicio"))
    html = resposta.content.decode("utf-8")

    assert resposta.status_code == 200
    assert minha.titulo in html
    assert "Minhas tarefas" in html
    assert "Equipe: 1 abertas, 1 atrasadas" in html
    resumo = carregar_resumo_tarefas(gestor, contrato)
    assert resumo["tarefas_minhas_total"] == 1
    assert resumo["tarefas_minhas"][0].pk == minha.pk
