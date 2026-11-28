from datetime import datetime, timedelta
from io import BytesIO

from openpyxl import load_workbook
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from contratos.models import Contrato, Participacao
from documentos.models import Documento


def _contrato(codigo="CT Á/Bloco 02"):
    return Contrato.objects.create(
        nome="Contrato de teste",
        codigo_interno=codigo,
        cliente="Cliente de teste",
    )


def _usuario(contrato, username="ana", *, primeiro_nome="Ana", sobrenome="Silva", staff=False):
    modelo = get_user_model()
    usuario = modelo.objects.create_user(
        username=username,
        password="senha",
        first_name=primeiro_nome,
        last_name=sobrenome,
        is_staff=staff,
    )
    if contrato is not None:
        Participacao.objects.create(
            usuario=usuario,
            contrato=contrato,
            papel=modelo.Perfil.ADMIN,
        )
    return usuario


def _documento(contrato, codigo, usuario, *, data_hora=None):
    documento = Documento(
        contrato=contrato,
        identificador_base=codigo,
        titulo="Título de teste",
    )
    documento._history_user = usuario
    if data_hora is not None:
        documento._history_date = data_hora
    documento.save()
    return documento


def _excel(response):
    workbook = load_workbook(BytesIO(response.content), data_only=False)
    planilha = workbook["Atividade"]
    return workbook, planilha


@pytest.mark.django_db
def test_baixa_excel_formatado_com_datas_reais_e_nome_seguro(client):
    contrato = _contrato()
    usuario = _usuario(contrato, primeiro_nome="José", sobrenome="Álvares")
    _documento(contrato, "DE-15.25.00.00-6A1-1001", usuario)
    client.force_login(usuario)

    resposta = client.get(
        reverse("atividade"), {"contrato": contrato.pk, "formato": "xlsx"}
    )

    workbook, planilha = _excel(resposta)
    assert resposta.status_code == 200
    assert resposta["Content-Type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert [celula.value for celula in planilha[1]] == [
        "Data e hora",
        "Pessoa",
        "Ação",
        "Evento",
        "Código do documento",
        "Resumo",
    ]
    assert planilha.max_row == 2
    assert planilha.freeze_panes == "A2"
    assert planilha.auto_filter.ref == "A1:F2"
    assert isinstance(planilha["A2"].value, datetime)
    assert planilha["A2"].value.strftime("%d/%m/%Y %H:%M") == timezone.localtime().strftime(
        "%d/%m/%Y %H:%M"
    )
    assert planilha["A2"].number_format == "dd/mm/yyyy hh:mm"
    assert planilha["B2"].value == "José Álvares"
    assert planilha["E2"].value == "DE-15.25.00.00-6A1-1001"
    assert planilha["A1"].font.bold
    assert planilha["A1"].fill.fill_type == "solid"
    assert all(planilha.column_dimensions[letra].width for letra in "ABCDEF")
    assert planilha.column_dimensions["F"].width <= 80
    nome_arquivo = (
        f'attachment; filename="atividade-ct-abloco-02-{timezone.localdate().isoformat()}.xlsx"'
    )
    assert resposta["Content-Disposition"] == nome_arquivo
    workbook.close()


@pytest.mark.django_db
def test_excel_reaproveita_filtros_de_pessoa_codigo_e_periodo(client):
    contrato = _contrato("CT-FILTROS")
    pessoa = _usuario(contrato, "ana", primeiro_nome="Ana")
    outra_pessoa = _usuario(contrato, "bia", primeiro_nome="Bia")
    codigo_incluido = "DE-15.25.00.00-6A1-1001"
    codigo_excluido = "DE-15.25.00.00-6A1-1002"
    _documento(contrato, codigo_incluido, pessoa)
    _documento(contrato, codigo_excluido, pessoa)
    _documento(
        contrato,
        "DE-15.25.00.00-6A1-11001",
        pessoa,
        data_hora=timezone.now() - timedelta(days=5),
    )
    _documento(contrato, "DE-15.25.00.00-6A1-2001", outra_pessoa)
    client.force_login(pessoa)

    resposta = client.get(
        reverse("atividade"),
        {
            "contrato": contrato.pk,
            "formato": "xlsx",
            "pessoa": pessoa.pk,
            "codigo": "1001",
            "de": timezone.localdate().isoformat(),
            "ate": timezone.localdate().isoformat(),
        },
    )

    _, planilha = _excel(resposta)
    assert planilha.max_row - 1 == 1
    assert [linha[4] for linha in planilha.iter_rows(min_row=2, values_only=True)] == [codigo_incluido]
    assert planilha["B2"].value == "Ana Silva"


@pytest.mark.django_db
def test_excel_exporta_todos_os_eventos_sem_limite_da_paginacao(client):
    contrato = _contrato("CT-MUITOS")
    usuario = _usuario(contrato)
    for numero in range(60):
        _documento(contrato, f"DE-15.25.00.00-6A1-{numero:04}", usuario)
    client.force_login(usuario)

    resposta = client.get(
        reverse("atividade"), {"contrato": contrato.pk, "formato": "xlsx"}
    )

    _, planilha = _excel(resposta)
    assert planilha.max_row - 1 == 60


@pytest.mark.django_db
def test_nao_participante_recebe_403_na_exportacao_excel(client):
    contrato = _contrato("CT-PRIVADO")
    usuario = _usuario(None, "externo")
    client.force_login(usuario)

    resposta = client.get(
        reverse("atividade"), {"contrato": contrato.pk, "formato": "xlsx"}
    )

    assert resposta.status_code == 403


@pytest.mark.django_db
def test_staff_baixa_excel_de_outro_contrato(client):
    contrato = _contrato("CT-OUTRO")
    autor = _usuario(contrato)
    codigo = "DE-15.25.00.00-6A1-3001"
    _documento(contrato, codigo, autor)
    staff = _usuario(None, "staff-b076", staff=True)
    client.force_login(staff)

    resposta = client.get(
        reverse("atividade"), {"contrato": contrato.pk, "formato": "xlsx"}
    )

    _, planilha = _excel(resposta)
    assert resposta.status_code == 200
    assert [linha[4] for linha in planilha.iter_rows(min_row=2, values_only=True)] == [codigo]


@pytest.mark.django_db
def test_link_excel_preserva_filtros_atuais(client):
    contrato = _contrato("CT-LINK")
    usuario = _usuario(contrato)
    client.force_login(usuario)

    resposta = client.get(
        reverse("atividade"),
        {
            "contrato": contrato.pk,
            "pessoa": usuario.pk,
            "acao": "criou",
            "de": timezone.localdate().isoformat(),
            "ate": timezone.localdate().isoformat(),
            "codigo": "1001",
        },
    )

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Baixar planilha (Excel)" in html
    assert (
        f'href="{reverse("atividade")}?contrato={contrato.pk}&amp;pessoa={usuario.pk}'
        in html
    )
    assert "formato=xlsx" in html
    assert "codigo=1001" in html


@pytest.mark.django_db
def test_parametro_csv_legado_baixa_excel(client):
    contrato = _contrato("CT-LEGADO")
    usuario = _usuario(contrato)
    client.force_login(usuario)

    resposta = client.get(
        reverse("atividade"), {"contrato": contrato.pk, "formato": "csv"}
    )

    assert resposta.status_code == 200
    assert resposta["Content-Type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert resposta["Content-Disposition"].endswith(".xlsx\"")
    _, planilha = _excel(resposta)
    assert planilha.title == "Atividade"
