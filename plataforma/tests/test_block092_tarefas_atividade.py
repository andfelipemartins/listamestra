from datetime import date, timedelta
from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from contratos.models import Contrato, Participacao
from documentos.models import Documento
from registro.servicos import carregar_eventos
from tarefas.servicos import cancelar_tarefa, concluir_tarefa, criar_tarefa


@pytest.fixture
def dados_tarefas(db, django_user_model):
    contrato = Contrato.objects.create(
        nome="Contrato de tarefas",
        codigo_interno="CT-BLOCK-092",
        cliente="Cliente de teste",
    )
    admin = django_user_model.objects.create_user(
        username="admin-092", first_name="Ana", last_name="Admin", password="senha"
    )
    responsavel = django_user_model.objects.create_user(
        username="responsavel-092",
        first_name="Bia",
        last_name="Responsável",
        password="senha",
    )
    sem_visibilidade = django_user_model.objects.create_user(
        username="externo-092", password="senha"
    )
    for usuario, papel in (
        (admin, get_user_model().Perfil.ADMIN),
        (responsavel, get_user_model().Perfil.EQUIPE),
        (sem_visibilidade, get_user_model().Perfil.EQUIPE),
    ):
        Participacao.objects.create(
            usuario=usuario, contrato=contrato, papel=papel, ativo=True
        )
    documento = Documento.objects.create(
        contrato=contrato,
        identificador_base="DE-15.25.00.00-6A1-1092",
        titulo="Desenho de teste",
    )
    return contrato, admin, responsavel, sem_visibilidade, documento


def _criar_tarefa(contrato, autor, responsavel, titulo, documento=None):
    return criar_tarefa(
        contrato=contrato,
        usuario=autor,
        titulo=titulo,
        descricao="",
        responsavel=responsavel,
        prazo=date.today() + timedelta(days=1),
        documento=documento,
    )


@pytest.mark.django_db
def test_criacao_conclusao_cancelamento_e_filtro_por_codigo_na_atividade(
    client, dados_tarefas
):
    contrato, admin, responsavel, _, documento = dados_tarefas
    tarefa_concluida = _criar_tarefa(
        contrato, admin, responsavel, "Revisar desenho", documento
    )
    tarefa_cancelada = _criar_tarefa(
        contrato, admin, responsavel, "Conferir outro item"
    )
    concluir_tarefa(tarefa=tarefa_concluida, usuario=responsavel)
    cancelar_tarefa(tarefa=tarefa_cancelada, usuario=admin)

    eventos = carregar_eventos(contrato, usuario=admin)
    eventos_tarefa = [evento for evento in eventos if evento["entidade"] == "tarefa"]
    assert [evento["acao"] for evento in eventos_tarefa].count("criou") == 2
    assert [evento["acao"] for evento in eventos_tarefa].count("concluiu") == 1
    assert [evento["acao"] for evento in eventos_tarefa].count("cancelou") == 1
    assert any(
        evento["usuario_nome"] == "Bia Responsável"
        and evento["acao"] == "concluiu"
        and "Revisar desenho" in evento["resumo"]
        and evento["codigo"] == documento.identificador_base
        for evento in eventos_tarefa
    )
    assert any(
        evento["usuario_nome"] == "Ana Admin"
        and evento["acao"] == "criou"
        and "Revisar desenho" in evento["resumo"]
        for evento in eventos_tarefa
    )
    assert all(timezone.is_aware(evento["data_hora"]) for evento in eventos_tarefa)

    client.force_login(admin)
    resposta = client.get(
        reverse("atividade"),
        {
            "contrato": contrato.pk,
            "pessoa": responsavel.pk,
            "acao": "concluiu",
            "de": timezone.localdate().isoformat(),
            "ate": timezone.localdate().isoformat(),
            "codigo": "1092",
        },
    )

    html = resposta.content.decode("utf-8")
    assert resposta.status_code == 200
    assert "Bia Responsável concluiu a tarefa “Revisar desenho”" in html
    assert "Conferir outro item" not in html


@pytest.mark.django_db
def test_eventos_de_tarefa_respeitam_visibilidade_e_entram_no_excel(
    client, dados_tarefas
):
    contrato, admin, responsavel, sem_visibilidade, documento = dados_tarefas
    tarefa = _criar_tarefa(
        contrato, admin, responsavel, "Preparar emissão", documento
    )
    concluir_tarefa(tarefa=tarefa, usuario=responsavel)

    eventos_ocultos = carregar_eventos(contrato, usuario=sem_visibilidade)
    assert not any(evento["entidade"] == "tarefa" for evento in eventos_ocultos)

    client.force_login(admin)
    resposta = client.get(
        reverse("atividade"), {"contrato": contrato.pk, "formato": "xlsx"}
    )
    workbook = load_workbook(BytesIO(resposta.content), data_only=True)
    linhas = list(workbook["Atividade"].iter_rows(min_row=2, values_only=True))
    workbook.close()

    linhas_tarefa = [linha for linha in linhas if "Preparar emissão" in linha[5]]
    assert resposta.status_code == 200
    assert len(linhas_tarefa) == 2
    assert {linha[2] for linha in linhas_tarefa} == {"Criou", "Concluiu"}
    assert all(linha[4] == documento.identificador_base for linha in linhas_tarefa)


@pytest.mark.django_db
def test_menu_inclui_tarefas_e_abre_lista_do_contrato_ativo(client, dados_tarefas):
    contrato, admin, _, _, _ = dados_tarefas
    client.force_login(admin)
    sessao = client.session
    sessao["contrato_ativo_id"] = contrato.pk
    sessao.save()

    inicio = client.get(reverse("inicio"))
    lista = client.get(reverse("tarefas:lista"))

    html = inicio.content.decode("utf-8")
    assert inicio.status_code == 200
    assert f'href="{reverse("tarefas:lista")}"' in html
    assert ">Tarefas</a>" in html
    assert lista.status_code == 200
    assert "Contrato de tarefas" in lista.content.decode("utf-8")
