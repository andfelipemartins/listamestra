import pytest
from django.urls import reverse

from contas.models import Usuario
from contratos.models import Contrato, Participacao
from importacoes.models import ImportacaoCronograma
from tests.importacoes_helpers import ativar_contrato


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato de importações",
        codigo_interno="CT-B086",
        cliente="Cliente de teste",
    )


@pytest.fixture
def outro_contrato(db):
    return Contrato.objects.create(
        nome="Outro contrato",
        codigo_interno="CT-B086-OUTRO",
        cliente="Outro cliente",
    )


@pytest.fixture
def staff(django_user_model):
    return django_user_model.objects.create_user(
        username="staff-b086",
        password="senha",
        is_staff=True,
    )


def test_menu_tem_apenas_uma_entrada_de_importacao_e_hub_tem_os_cinco_cartoes(
    client, contrato, staff
):
    client.force_login(staff)
    ativar_contrato(client, contrato)

    resposta = client.get(reverse("importacoes_home"))

    assert resposta.status_code == 200
    html = resposta.content.decode("utf-8")
    menu = html.split("<aside", 1)[1].split("</aside>", 1)[0]
    assert menu.count(">Importações</a>") == 1
    for entrada_removida in (
        "Importar ID",
        "Importar situação PW",
        "Atualizar situação (planilha)",
        "Importar cronograma",
        "Acervo de feriados",
        "Participações",
    ):
        assert entrada_removida not in menu
    for cartao in (
        "Índice de Documentos (ID)",
        "Situação PW",
        "Situação por planilha padrão",
        "Cronograma",
        "Elaboração da Lista Mestra",
    ):
        assert cartao in html
    assert f'href="{reverse("historico_importacoes", args=(contrato.pk,))}"' in html
    assert "Contrato:</strong> CT-B086" in html


@pytest.mark.parametrize(
    "url_name",
    (
        "importar_id",
        "importar_situacao_pw",
        "importar_situacao_padrao",
        "importar_cronograma",
        "importar_elaboracao",
    ),
)
def test_importacao_mostra_contrato_da_sessao_e_nao_exibe_campo_contrato(
    client, contrato, staff, url_name
):
    client.force_login(staff)
    ativar_contrato(client, contrato)

    resposta = client.get(reverse(url_name))

    assert resposta.status_code == 200
    html = resposta.content.decode("utf-8")
    assert "Contrato:</strong> CT-B086" in html
    assert 'name="contrato"' not in html


@pytest.mark.parametrize(
    "url_name",
    (
        "importacoes_home",
        "importar_id",
        "importar_situacao_pw",
        "importar_situacao_padrao",
        "importar_cronograma",
        "importar_elaboracao",
    ),
)
def test_importacoes_sem_contrato_ativo_redirecionam_para_home(
    client, staff, url_name
):
    client.force_login(staff)

    resposta = client.get(reverse(url_name))

    assert resposta.status_code == 302
    assert resposta.url == reverse("contratos_escolher")


def test_importacao_e_historico_barram_usuario_sem_permissao_no_contrato_ativo(
    client, contrato, outro_contrato, django_user_model
):
    usuario = django_user_model.objects.create_user(
        username="b086-sem-permissao",
        password="senha",
    )
    Participacao.objects.create(
        usuario=usuario,
        contrato=outro_contrato,
        papel=Usuario.Perfil.ADMIN,
        ativo=True,
    )
    client.force_login(usuario)
    ativar_contrato(client, contrato)

    assert client.get(reverse("importacoes_home")).status_code == 403
    assert client.get(reverse("importar_situacao_padrao")).status_code == 403


def test_historico_usa_o_contrato_ativo_mesmo_quando_url_aponta_para_outro(
    client, contrato, outro_contrato, staff
):
    ImportacaoCronograma.objects.create(contrato=contrato, arquivo_nome="ativo.xlsx")
    ImportacaoCronograma.objects.create(
        contrato=outro_contrato,
        arquivo_nome="outro-contrato.xlsx",
    )
    client.force_login(staff)
    ativar_contrato(client, contrato)

    resposta = client.get(reverse("historico_importacoes", args=(outro_contrato.pk,)))

    assert resposta.status_code == 200
    assert "ativo.xlsx" in resposta.content.decode("utf-8")
    assert "outro-contrato.xlsx" not in resposta.content.decode("utf-8")
