from datetime import date, datetime
from pathlib import Path

import pytest
import yaml
from django.urls import reverse

from contas.models import Usuario
from contratos.models import Contrato, Participacao, PerfilContrato
from documentos.models import (
    Documento,
    Emissao,
    ListaMestraConfiguracao,
)
from documentos.servicos import catalogo_colunas_lista_mestra


PERFIL_METRO = (
    Path(__file__).resolve().parents[2] / "core" / "perfil" / "exemplos" / "metro.yaml"
)


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato para colunas",
        codigo_interno="CT-COLUNAS",
        cliente="Cliente de teste",
    )


@pytest.fixture
def perfil_modelo(contrato):
    with PERFIL_METRO.open(encoding="utf-8") as arquivo:
        definicao = _json_compatibilidade(yaml.safe_load(arquivo))
    definicao["vigencia_inicio"] = "2020-01-01"
    return PerfilContrato.objects.create(
        contrato=contrato,
        versao=1,
        vigencia_inicio=date(2020, 1, 1),
        definicao=definicao,
    )


@pytest.fixture
def equipe(contrato, django_user_model):
    usuario = django_user_model.objects.create_user(
        username="equipe-colunas",
        password="senha-segura",
    )
    Participacao.objects.create(
        usuario=usuario,
        contrato=contrato,
        papel=Usuario.Perfil.EQUIPE,
        ativo=True,
    )
    return usuario


@pytest.fixture
def administrador(contrato, django_user_model):
    usuario = django_user_model.objects.create_user(
        username="admin-colunas",
        password="senha-segura",
    )
    Participacao.objects.create(
        usuario=usuario,
        contrato=contrato,
        papel=Usuario.Perfil.ADMIN,
        ativo=True,
    )
    return usuario


@pytest.fixture
def emissao(contrato, perfil_modelo):
    documento = Documento.objects.create(
        contrato=contrato,
        identificador_base="DE-15.25.00.00-6A1-1001",
        tipo="DE",
        titulo="Título de teste",
        disciplina="A1",
        atributos={
            "tipo": "DE",
            "linha": "15",
            "trecho": "25",
            "subtrecho": "00",
            "unidade": "00",
            "etapa": "6",
            "classe": "A",
            "subclasse": "1",
            "sequencial": "1001",
        },
    )
    return Emissao.objects.create(
        documento=documento,
        revisao="1",
        versao=1,
        fase=Emissao.Fase.ORIGINAL,
        data_emissao=date(2026, 1, 1),
        origem=Emissao.Origem.CLIENTE,
    )


def _json_compatibilidade(valor):
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {chave: _json_compatibilidade(item) for chave, item in valor.items()}
    if isinstance(valor, list):
        return [_json_compatibilidade(item) for item in valor]
    return valor


def _catalogo(perfil_modelo):
    from core.perfil import perfil_de_dict

    return catalogo_colunas_lista_mestra(perfil_de_dict(perfil_modelo.definicao))


@pytest.mark.django_db
def test_lista_mestra_sem_configuracao_mantem_colunas_padrao(
    client, contrato, perfil_modelo, equipe, emissao
):
    client.force_login(equipe)

    resposta = client.get(reverse("lista_mestra"), {"contrato": contrato.pk})

    assert resposta.status_code == 200
    assert resposta.context["chaves_visiveis"] == [
        coluna["chave"] for coluna in _catalogo(perfil_modelo)
    ]
    html = resposta.content.decode("utf-8")
    for rotulo in ("Código", "Título", "Elabora&#231;&#227;o", "Revisão", "GRD"):
        assert rotulo in html
    assert "Distribuição por setor" in html


@pytest.mark.django_db
def test_lista_mestra_oculta_elaboracao_e_reordena_titulo_apos_revisao(
    client, contrato, perfil_modelo, administrador, emissao
):
    catalogo = _catalogo(perfil_modelo)
    chaves = [coluna["chave"] for coluna in catalogo]
    chaves.remove("elaboracao")
    chaves.remove("titulo")
    chaves.insert(chaves.index("revisao") + 1, "titulo")
    ListaMestraConfiguracao.objects.create(
        contrato=contrato,
        chaves_visiveis=chaves,
        chaves_catalogo=[coluna["chave"] for coluna in catalogo],
    )
    client.force_login(administrador)

    resposta = client.get(reverse("lista_mestra"), {"contrato": contrato.pk})

    assert resposta.status_code == 200
    html = resposta.content.decode("utf-8")
    assert "Elaboração" not in html
    assert html.index(">Código</th>") < html.index(">Revisão</th>")
    assert html.index(">Revisão</th>") < html.index(">Título</th>")
    corpo = html.split("<tbody>", 1)[1]
    pos_titulo = corpo.index('title="Título de teste"')
    assert corpo.rfind(">1</td>", 0, pos_titulo) < pos_titulo
    assert emissao.documento.identificador_base in html


@pytest.mark.django_db
def test_tela_de_colunas_restringe_acesso_a_staff_ou_admin(
    client, contrato, perfil_modelo, equipe, administrador, django_user_model
):
    url = reverse("lista_mestra_colunas")
    client.force_login(equipe)

    resposta_equipe = client.get(url, {"contrato": contrato.pk})
    lista_equipe = client.get(reverse("lista_mestra"), {"contrato": contrato.pk})

    assert resposta_equipe.status_code == 403
    assert "lista_mestra_colunas" not in lista_equipe.content.decode("utf-8")

    client.force_login(administrador)
    resposta_admin = client.get(url, {"contrato": contrato.pk})
    assert resposta_admin.status_code == 200
    assert "Colunas da Lista Mestra" in resposta_admin.content.decode("utf-8")

    staff = django_user_model.objects.create_user(
        username="staff-colunas",
        password="senha-segura",
        is_staff=True,
    )
    client.force_login(staff)
    resposta_staff = client.get(url, {"contrato": contrato.pk})
    assert resposta_staff.status_code == 200


@pytest.mark.django_db
def test_voltar_ao_padrao_remove_a_configuracao(
    client, contrato, perfil_modelo, administrador
):
    catalogo = _catalogo(perfil_modelo)
    ListaMestraConfiguracao.objects.create(
        contrato=contrato,
        chaves_visiveis=["codigo", "revisao"],
        chaves_catalogo=[coluna["chave"] for coluna in catalogo],
    )
    client.force_login(administrador)

    resposta = client.post(
        f"{reverse('lista_mestra_colunas')}?contrato={contrato.pk}",
        {"contrato": contrato.pk, "acao": "padrao"},
    )

    assert resposta.status_code == 302
    assert resposta["Location"] == f"{reverse('lista_mestra')}?contrato={contrato.pk}"
    assert not ListaMestraConfiguracao.objects.filter(contrato=contrato).exists()


@pytest.mark.django_db
def test_tela_salva_visibilidade_e_ordem_selecionadas(
    client, contrato, perfil_modelo, administrador
):
    catalogo = _catalogo(perfil_modelo)
    ordem = [coluna["chave"] for coluna in catalogo if coluna["chave"] != "codigo"]
    ordem.remove("elaboracao")
    ordem.remove("titulo")
    ordem.insert(ordem.index("revisao") + 1, "titulo")
    client.force_login(administrador)

    resposta = client.post(
        f"{reverse('lista_mestra_colunas')}?contrato={contrato.pk}",
        {
            "contrato": contrato.pk,
            "acao": "salvar",
            "visiveis": ordem,
            "ordem": "\n".join(ordem),
        },
    )

    configuracao = ListaMestraConfiguracao.objects.get(contrato=contrato)
    assert resposta.status_code == 302
    assert configuracao.chaves_visiveis == ["codigo", *ordem]
    assert configuracao.chaves_catalogo == [coluna["chave"] for coluna in catalogo]


@pytest.mark.django_db
def test_chave_desconhecida_e_ignorada_e_coluna_nova_entra_no_fim(
    client, contrato, perfil_modelo, equipe, emissao
):
    catalogo = _catalogo(perfil_modelo)
    chaves_catalogo = [coluna["chave"] for coluna in catalogo]
    conhecidas = [chave for chave in chaves_catalogo if chave != "observacao"]
    ListaMestraConfiguracao.objects.create(
        contrato=contrato,
        chaves_visiveis=["codigo", "revisao", "chave_removida"],
        chaves_catalogo=conhecidas,
    )
    client.force_login(equipe)

    resposta = client.get(reverse("lista_mestra"), {"contrato": contrato.pk})

    assert resposta.status_code == 200
    assert resposta.context["chaves_visiveis"] == [
        "codigo",
        "revisao",
        "observacao",
    ]
    assert emissao.documento.identificador_base in resposta.content.decode("utf-8")
