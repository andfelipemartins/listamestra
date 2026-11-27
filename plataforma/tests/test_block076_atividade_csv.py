import csv
from datetime import timedelta
from io import StringIO

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


def _csv(response):
    texto = response.content.decode("utf-8-sig")
    leitor = csv.DictReader(StringIO(texto, newline=""), delimiter=";")
    return texto, leitor.fieldnames, list(leitor)


@pytest.mark.django_db
def test_baixa_csv_com_bom_cabecalho_separador_data_e_nome_seguro(client):
    contrato = _contrato()
    usuario = _usuario(contrato, primeiro_nome="José", sobrenome="Álvares")
    _documento(contrato, "DE-15.25.00.00-6A1-1001", usuario)
    client.force_login(usuario)

    resposta = client.get(
        reverse("atividade"), {"contrato": contrato.pk, "formato": "csv"}
    )

    texto, cabecalho, linhas = _csv(resposta)
    assert resposta.status_code == 200
    assert resposta.content.startswith(b"\xef\xbb\xbf")
    assert cabecalho == [
        "Data e hora",
        "Pessoa",
        "Ação",
        "Evento",
        "Código do documento",
        "Resumo",
    ]
    assert ";" in texto
    assert linhas[0]["Data e hora"] == timezone.localtime().strftime("%d/%m/%Y %H:%M")
    assert linhas[0]["Pessoa"] == "José Álvares"
    assert linhas[0]["Código do documento"] == "DE-15.25.00.00-6A1-1001"
    nome_arquivo = (
        f'attachment; filename="atividade-ct-abloco-02-{timezone.localdate().isoformat()}.csv"'
    )
    assert resposta["Content-Disposition"] == nome_arquivo


@pytest.mark.django_db
def test_csv_reaproveita_filtros_de_pessoa_codigo_e_periodo(client):
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
            "formato": "csv",
            "pessoa": pessoa.pk,
            "codigo": "1001",
            "de": timezone.localdate().isoformat(),
            "ate": timezone.localdate().isoformat(),
        },
    )

    _, _, linhas = _csv(resposta)
    assert [linha["Código do documento"] for linha in linhas] == [codigo_incluido]
    assert linhas[0]["Pessoa"] == "Ana Silva"


@pytest.mark.django_db
def test_csv_exporta_todos_os_eventos_sem_limite_da_paginacao(client):
    contrato = _contrato("CT-MUITOS")
    usuario = _usuario(contrato)
    for numero in range(60):
        _documento(contrato, f"DE-15.25.00.00-6A1-{numero:04}", usuario)
    client.force_login(usuario)

    resposta = client.get(
        reverse("atividade"), {"contrato": contrato.pk, "formato": "csv"}
    )

    _, _, linhas = _csv(resposta)
    assert len(linhas) == 60


@pytest.mark.django_db
def test_nao_participante_recebe_403_no_csv(client):
    contrato = _contrato("CT-PRIVADO")
    usuario = _usuario(None, "externo")
    client.force_login(usuario)

    resposta = client.get(
        reverse("atividade"), {"contrato": contrato.pk, "formato": "csv"}
    )

    assert resposta.status_code == 403


@pytest.mark.django_db
def test_staff_baixa_csv_de_outro_contrato(client):
    contrato = _contrato("CT-OUTRO")
    autor = _usuario(contrato)
    codigo = "DE-15.25.00.00-6A1-3001"
    _documento(contrato, codigo, autor)
    staff = _usuario(None, "staff-b076", staff=True)
    client.force_login(staff)

    resposta = client.get(
        reverse("atividade"), {"contrato": contrato.pk, "formato": "csv"}
    )

    _, _, linhas = _csv(resposta)
    assert resposta.status_code == 200
    assert [linha["Código do documento"] for linha in linhas] == [codigo]


@pytest.mark.django_db
def test_link_csv_preserva_filtros_atuais(client):
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
    assert "Baixar planilha (CSV)" in html
    assert (
        f'href="{reverse("atividade")}?contrato={contrato.pk}&amp;pessoa={usuario.pk}'
        in html
    )
    assert "formato=csv" in html
    assert "codigo=1001" in html
