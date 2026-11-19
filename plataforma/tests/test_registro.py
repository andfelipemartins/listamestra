import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from contratos.models import Contrato, Participacao
from documentos.models import Documento
from importacoes.models import ImportacaoID, IndiceDocumentos, ItemPrevisto
from registro.servicos import carregar_eventos


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato de atividade",
        codigo_interno="CT-ATIVIDADE",
        cliente="Cliente de teste",
    )


@pytest.fixture
def usuario(contrato):
    modelo = get_user_model()
    usuario = modelo.objects.create_user(
        username="ana",
        first_name="Ana",
        last_name="Silva",
        password="senha",
    )
    Participacao.objects.create(
        usuario=usuario,
        contrato=contrato,
        papel=modelo.Perfil.EQUIPE,
    )
    return usuario


def _documento(contrato, codigo, titulo, usuario=None):
    documento = Documento(
        contrato=contrato,
        identificador_base=codigo,
        titulo=titulo,
    )
    documento._history_user = usuario
    documento.save()
    return documento


@pytest.mark.django_db
def test_alteracao_de_titulo_gera_evento_com_diff(contrato, usuario):
    documento = _documento(contrato, "DE-15.25.00.00-6A1-1001", "Título anterior", usuario)
    documento.titulo = "Título novo"
    documento._history_user = usuario
    documento.save(update_fields=("titulo",))

    evento = next(
        item
        for item in carregar_eventos(contrato)
        if item["acao"] == "alterou" and item["codigo"] == documento.identificador_base
    )

    assert evento["usuario_nome"] == "Ana Silva"
    assert evento["resumo"] == f"Ana Silva alterou o título de {documento.identificador_base}"
    assert evento["detalhes"] == [
        {"campo": "título", "antes": "Título anterior", "depois": "Título novo"}
    ]


@pytest.mark.django_db
def test_importacao_id_aparece_como_um_evento_para_o_lote(contrato, usuario):
    indice = IndiceDocumentos.objects.create(
        contrato=contrato,
        codigo="ID-ATIVIDADE",
        revisao="1",
        fonte=IndiceDocumentos.Fonte.EXCEL_ID,
        arquivo_nome="ID-atividade.xlsx",
        importado_em=timezone.now(),
        importado_por=usuario,
    )
    for numero in range(3):
        documento = _documento(contrato, f"DE-15.25.00.00-6A1-10{numero:02}", f"Doc {numero}")
        ItemPrevisto.objects.create(indice=indice, documento=documento, titulo=documento.titulo)
    ImportacaoID.objects.create(
        contrato=contrato,
        indice=indice,
        arquivo_nome="ID-atividade.xlsx",
        importado_por=usuario,
        linhas_validas=3,
        linhas_invalidas=2,
    )

    importacoes = [evento for evento in carregar_eventos(contrato) if evento["acao"] == "importou"]

    assert len(importacoes) == 1
    assert importacoes[0]["resumo"] == "Ana Silva importou ID ID-atividade.xlsx: 3 válidas, 2 recusadas"
    assert importacoes[0]["link_recusadas"] is True


@pytest.mark.django_db
def test_filtros_por_pessoa_acao_periodo_e_codigo(client, contrato, usuario):
    documento = _documento(contrato, "DE-15.25.00.00-6A1-1001", "Título inicial", usuario)
    documento.titulo = "Título atualizado"
    documento._history_user = usuario
    documento.save(update_fields=("titulo",))
    outro = _documento(contrato, "MC-15.25.00.00-6A1-1002", "Outro documento", usuario)
    outro.titulo = "Outro título atualizado"
    outro._history_user = usuario
    outro.save(update_fields=("titulo",))

    client.force_login(usuario)
    resposta = client.get(
        reverse("atividade"),
        {
            "contrato": contrato.pk,
            "pessoa": usuario.pk,
            "acao": "alterou",
            "de": timezone.localdate().isoformat(),
            "ate": timezone.localdate().isoformat(),
            "codigo": "1001",
        },
    )

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "alterou o título de DE-15.25.00.00-6A1-1001" in html
    assert "MC-15.25.00.00-6A1-1002" not in html


@pytest.mark.django_db
def test_acesso_exige_participacao_e_staff_pode_ver_outros_contratos(client, contrato):
    modelo = get_user_model()
    sem_participacao = modelo.objects.create_user(username="externo", password="senha")
    client.force_login(sem_participacao)
    assert client.get(reverse("atividade"), {"contrato": contrato.pk}).status_code == 403

    staff = modelo.objects.create_user(username="staff", password="senha", is_staff=True)
    client.force_login(staff)
    resposta = client.get(reverse("atividade"), {"contrato": contrato.pk})
    assert resposta.status_code == 200
