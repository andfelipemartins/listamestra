from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from acoes.models import AcaoPendencia
from acoes.services import (
    JANELA_TITULO_DIFERENTE_ID,
    PENDENCIA_TITULO_DIFERENTE_ID,
    carregar_ignorados,
    carregar_minha_mesa,
)
from contas.models import Usuario
from contratos.models import Contrato, Participacao
from documentos.models import Documento
from importacoes.models import IndiceDocumentos, ItemPrevisto
from registro.servicos import carregar_eventos


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato do block-075",
        codigo_interno="CT-B075",
        cliente="Cliente de teste",
    )


@pytest.fixture
def admin_contrato(contrato, django_user_model):
    usuario = django_user_model.objects.create_user(
        username="admin-block075",
        password="senha",
        first_name="Ana",
        last_name="Administradora",
    )
    Participacao.objects.create(
        usuario=usuario,
        contrato=contrato,
        papel=Usuario.Perfil.ADMIN,
        ativo=True,
    )
    return usuario


@pytest.fixture
def equipe(contrato, django_user_model):
    usuario = django_user_model.objects.create_user(
        username="equipe-block075",
        password="senha",
    )
    Participacao.objects.create(
        usuario=usuario,
        contrato=contrato,
        papel=Usuario.Perfil.EQUIPE,
        ativo=True,
    )
    return usuario


def _indice(contrato, codigo, *, importado_em=None, vigente=True, substituido_por=None):
    return IndiceDocumentos.objects.create(
        contrato=contrato,
        codigo=codigo,
        revisao="1",
        fonte=IndiceDocumentos.Fonte.EXCEL_ID,
        arquivo_nome=f"{codigo}.xlsx",
        importado_em=importado_em or timezone.now(),
        vigente=vigente,
        substituido_por=substituido_por,
    )


def _documento(contrato, codigo, titulo="Título atual"):
    return Documento.objects.create(
        contrato=contrato,
        identificador_base=codigo,
        tipo="DE",
        titulo=titulo,
    )


def _item(indice, documento, titulo="Título do ID", *, excluido=False):
    return ItemPrevisto.objects.create(
        indice=indice,
        documento=documento,
        titulo=titulo,
        excluido=excluido,
    )


def _janela(mesa):
    return next(
        janela for janela in mesa["janelas"]
        if janela["id"] == JANELA_TITULO_DIFERENTE_ID
    )


@pytest.mark.django_db
def test_titulo_diferente_aparece_com_dados_do_id_mais_recente(
    contrato, admin_contrato
):
    documento = _documento(contrato, "DOC-075-1001")
    antigo = _indice(
        contrato,
        "ID-ANTIGO",
        importado_em=timezone.now() - timedelta(days=1),
    )
    recente = _indice(contrato, "ID-RECENTE")
    _item(antigo, documento, "Título anterior do ID")
    _item(recente, documento, "  Título atual do ID  ")

    janela = _janela(carregar_minha_mesa(admin_contrato, contrato.pk, limite=None))

    assert janela["quantidade"] == 1
    item = janela["todos"][0]
    assert item["tipo_pendencia"] == PENDENCIA_TITULO_DIFERENTE_ID
    assert item["codigo"] == documento.identificador_base
    assert item["titulo_atual"] == "Título atual"
    assert item["titulo_id"] == "Título atual do ID"
    assert item["codigo_id"] == "ID-RECENTE"
    assert item["nome_id"] == "ID-RECENTE.xlsx"


@pytest.mark.django_db
def test_nao_aparece_quando_diferenca_e_apenas_de_maiusculas_ou_espacos(
    contrato, admin_contrato
):
    indice = _indice(contrato, "ID-075")
    documento = _documento(contrato, "DOC-075-1002", "  TÍTULO DO ID ")
    _item(indice, documento, "Título do ID")

    janela = _janela(carregar_minha_mesa(admin_contrato, contrato.pk, limite=None))

    assert janela["todos"] == []
    assert janela["quantidade"] == 0


@pytest.mark.django_db
@pytest.mark.parametrize("cenario", ["excluido", "titulo_vazio", "substituido"])
def test_nao_aparece_para_item_excluido_titulo_vazio_ou_indice_substituido(
    contrato, admin_contrato, cenario
):
    documento = _documento(contrato, f"DOC-075-{cenario}")
    indice = _indice(
        contrato,
        f"ID-075-{cenario}",
        vigente=cenario != "substituido",
        substituido_por=(
            _indice(contrato, "ID-075-ATUAL") if cenario == "substituido" else None
        ),
    )
    _item(
        indice,
        documento,
        titulo="   " if cenario == "titulo_vazio" else "Título do ID",
        excluido=cenario == "excluido",
    )

    janela = _janela(carregar_minha_mesa(admin_contrato, contrato.pk, limite=None))

    assert janela["todos"] == []


@pytest.mark.django_db
def test_usar_titulo_id_recalcula_salva_motivo_atividade_e_remove_pendencia(
    client, contrato, admin_contrato
):
    indice = _indice(contrato, "ID-075-CONCILIACAO")
    documento = _documento(contrato, "DOC-075-1003")
    _item(indice, documento, "Título correto do ID")
    client.force_login(admin_contrato)

    resposta = client.post(
        reverse("acoes:usar_titulo_id"),
        {
            "contrato": contrato.pk,
            "documento": documento.pk,
            "titulo": "Título falsificado no POST",
        },
        follow=True,
    )

    assert resposta.status_code == 200
    assert "Título atualizado conforme o ID." in resposta.content.decode()
    documento.refresh_from_db()
    assert documento.titulo == "Título correto do ID"
    evento = next(
        item for item in carregar_eventos(contrato)
        if item["acao_rotulo"] == "Título alterado"
    )
    assert evento["detalhes"][-1] == {
        "campo": "Motivo",
        "antes": "",
        "depois": "Conciliação com o ID ID-075-CONCILIACAO",
    }
    assert _janela(
        carregar_minha_mesa(admin_contrato, contrato.pk, limite=None)
    )["todos"] == []


@pytest.mark.django_db
def test_manter_atual_exige_motivo_e_pendencia_ignorada_pode_reativar(
    client, contrato, equipe
):
    indice = _indice(contrato, "ID-075-MANTER")
    documento = _documento(contrato, "DOC-075-1004")
    _item(indice, documento, "Título do ID")
    client.force_login(equipe)
    payload = {
        "contrato": contrato.pk,
        "documento": documento.pk,
        "tipo_pendencia": PENDENCIA_TITULO_DIFERENTE_ID,
        "acao": AcaoPendencia.Acao.IGNORAR,
    }
    url = reverse("acoes:registrar_acao")
    pendencias = client.get(reverse("acoes:pendencias"), {"contrato": contrato.pk})
    assert "Manter o atual" in pendencias.content.decode()

    sem_motivo = client.post(url, payload, follow=True)
    assert "Informe o motivo para ignorar a pendência." in sem_motivo.content.decode()
    assert _janela(carregar_minha_mesa(equipe, contrato.pk, limite=None))["quantidade"] == 1

    resposta = client.post(url, {**payload, "motivo": "Manter o título validado"}, follow=True)

    assert resposta.status_code == 200
    assert "Pendência ignorada." in resposta.content.decode()
    assert _janela(carregar_minha_mesa(equipe, contrato.pk, limite=None))["todos"] == []
    ignorados = carregar_ignorados(equipe, contrato.pk)["janela"]
    item_ignorado = next(item for item in ignorados["todos"] if item["documento"].pk == documento.pk)
    assert item_ignorado["ultima_acao"].motivo == "Manter o título validado"

    pagina_ignorados = client.get(reverse("acoes:ignorados"), {"contrato": contrato.pk})
    assert pagina_ignorados.status_code == 200
    assert "Título do ID" in pagina_ignorados.content.decode()
    client.post(
        reverse("acoes:reativar"),
        {
            "contrato": contrato.pk,
            "documento": documento.pk,
            "tipo_pendencia": PENDENCIA_TITULO_DIFERENTE_ID,
        },
    )
    assert _janela(carregar_minha_mesa(equipe, contrato.pk, limite=None))["quantidade"] == 1


@pytest.mark.django_db
def test_sem_permissao_de_editar_titulo_nao_ve_botao_e_recebe_403(
    client, contrato, equipe
):
    indice = _indice(contrato, "ID-075-PERMISSAO")
    documento = _documento(contrato, "DOC-075-1005")
    _item(indice, documento, "Título do ID")
    client.force_login(equipe)
    url_pendencias = reverse("acoes:pendencias")
    html = client.get(url_pendencias, {"contrato": contrato.pk}).content.decode()

    assert "Título diferente do ID" in html
    assert "Usar o título do ID" not in html
    client.raise_request_exception = False
    resposta = client.post(
        reverse("acoes:usar_titulo_id"),
        {"contrato": contrato.pk, "documento": documento.pk},
    )

    assert resposta.status_code == 403
    documento.refresh_from_db()
    assert documento.titulo == "Título atual"


@pytest.mark.django_db
def test_nao_participante_recebe_403_na_conciliacao(
    client, contrato, django_user_model
):
    usuario = django_user_model.objects.create_user(username="fora-block075", password="senha")
    client.force_login(usuario)
    client.raise_request_exception = False

    resposta = client.post(
        reverse("acoes:usar_titulo_id"),
        {"contrato": contrato.pk, "documento": 1},
    )

    assert resposta.status_code == 403


@pytest.mark.django_db
def test_secao_tem_card_contagem_e_tela_filtrada(client, contrato, admin_contrato):
    indice = _indice(contrato, "ID-075-CARD")
    documento = _documento(contrato, "DOC-075-1006")
    _item(indice, documento, "Título do ID")
    client.force_login(admin_contrato)

    pendencias = client.get(reverse("acoes:pendencias"), {"contrato": contrato.pk})
    html = pendencias.content.decode()
    assert pendencias.status_code == 200
    assert f'id="janela-{JANELA_TITULO_DIFERENTE_ID}"' in html
    assert "Título diferente do ID" in html
    assert "1 item" in html

    detalhe = client.get(
        reverse("acoes:janela", args=(JANELA_TITULO_DIFERENTE_ID,)),
        {"contrato": contrato.pk},
    )
    assert detalhe.status_code == 200
    assert documento.identificador_base in detalhe.content.decode()
    assert "Usar o título do ID" in detalhe.content.decode()


@pytest.mark.django_db
def test_consulta_da_secao_nao_faz_n_plus_um(contrato, django_user_model):
    indice = _indice(contrato, "ID-075-QUERIES")
    usuario = django_user_model.objects.create_user(
        username="staff-queries-block075",
        password="senha",
        is_staff=True,
    )
    primeiro = _documento(contrato, "DOC-075-2000")
    _item(indice, primeiro)
    with CaptureQueriesContext(connection) as consultas_unico:
        carregar_minha_mesa(usuario, contrato.pk, limite=None)

    for numero in range(1, 9):
        documento = _documento(contrato, f"DOC-075-{2000 + numero}")
        _item(indice, documento)
    with CaptureQueriesContext(connection) as consultas_varios:
        mesa = carregar_minha_mesa(usuario, contrato.pk, limite=None)

    assert _janela(mesa)["quantidade"] == 9
    assert len(consultas_varios) == len(consultas_unico)
