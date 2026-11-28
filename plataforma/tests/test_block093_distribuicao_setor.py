from datetime import date, datetime
from pathlib import Path

import pytest
import yaml
from django.urls import reverse

from contas.models import Usuario
from contratos.models import Contrato, Participacao, PerfilContrato
from documentos.models import Documento, Emissao
from documentos.servicos import carregar_lista_mestra
from grds.forms import GrdConfiguracaoForm
from grds.models import Grd, GrdItem
from grds.servicos import (
    SETORES_DISTRIBUICAO_PADRAO,
    garantir_configuracao_grd,
    listar_setores_distribuicao,
)


PERFIL_METRO = Path(__file__).resolve().parents[2] / "core" / "perfil" / "exemplos" / "metro.yaml"
CODIGO = "DE-15.25.00.00-6A1-1001"


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato distribuição",
        codigo_interno="CT-D093",
        cliente="Cliente de teste",
    )


@pytest.fixture
def perfil_modelo(contrato):
    with PERFIL_METRO.open(encoding="utf-8") as arquivo:
        definicao = _json_compatibility(yaml.safe_load(arquivo))
    return PerfilContrato.objects.create(
        contrato=contrato,
        versao=1,
        vigencia_inicio=date(2020, 1, 1),
        definicao=definicao,
    )


@pytest.fixture
def admin_contrato(contrato, django_user_model):
    usuario = django_user_model.objects.create_user(
        username="admin-d093", password="senha", first_name="Érica"
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
        username="equipe-d093", password="senha"
    )
    Participacao.objects.create(
        usuario=usuario,
        contrato=contrato,
        papel=Usuario.Perfil.EQUIPE,
        ativo=True,
    )
    return usuario


def _json_compatibility(valor):
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {chave: _json_compatibility(item) for chave, item in valor.items()}
    if isinstance(valor, list):
        return [_json_compatibility(item) for item in valor]
    return valor


def _documento(contrato, codigo=CODIGO, titulo="Planta de implantação"):
    return Documento.objects.create(
        contrato=contrato,
        identificador_base=codigo,
        titulo=titulo,
        tipo="DE",
        trecho="25",
        disciplina="A1",
        atributos={
            "tipo": "DE",
            "linha": "15",
            "trecho": "25",
            "subtrecho": "00",
            "unidade": "00",
            "etapa": "6",
            "classe": "A1",
            "sequencial": codigo[-4:],
        },
    )


def _emissao(documento, revisao, data_emissao):
    return Emissao.objects.create(
        documento=documento,
        revisao=revisao,
        versao=1,
        fase=Emissao.Fase.ORIGINAL,
        data_emissao=data_emissao,
        origem=Emissao.Origem.INTERNA,
    )


def _grd(contrato, numero, data, setor):
    return Grd.objects.create(
        contrato=contrato,
        numero=numero,
        data=data,
        destinatario="Cliente",
        setor=setor,
    )


@pytest.mark.django_db
def test_setores_padrao_quando_vazios_e_edicao_da_lista(contrato):
    configuracao = garantir_configuracao_grd(contrato)
    assert configuracao.setores_distribuicao == []
    assert listar_setores_distribuicao(configuracao) == list(SETORES_DISTRIBUICAO_PADRAO)

    form = GrdConfiguracaoForm(
        data={
            "nome_emitente": "Consórcio L15",
            "titulo": "Guia de Remessa",
            "formato_numero": "{sigla} {seq:03d}/{ano}",
            "formatos_copias": ["A1", "Digital"],
            "setores_distribuicao_texto": "Instrumentação\nProdução\nQualidade",
        },
        instance=configuracao,
    )

    assert form.is_valid(), form.errors
    configuracao = form.save()
    assert listar_setores_distribuicao(configuracao) == [
        {"nome": "Instrumentação", "ordem": 1},
        {"nome": "Produção", "ordem": 2},
        {"nome": "Qualidade", "ordem": 3},
    ]


@pytest.mark.django_db
def test_cria_grd_com_setor_e_filtra_lista(
    client, contrato, perfil_modelo, admin_contrato
):
    documento = _documento(contrato)
    _emissao(documento, "1", date(2026, 10, 1))
    client.force_login(admin_contrato)
    session = client.session
    session["contrato_ativo_id"] = contrato.pk
    session.save()
    dados = {
        "contrato": contrato.pk,
        "data": "2026-11-27",
        "destinatario": "Equipe de produção",
        "setor_destino": "Produção",
        "observacao": "",
        "texto_codigos": CODIGO,
        "etapa": "previa",
    }

    previa = client.post(reverse("grds:nova"), dados)
    dados["etapa"] = "confirmar"
    confirmacao = client.post(reverse("grds:nova"), dados)
    grd = Grd.objects.get(contrato=contrato)

    assert previa.status_code == 200
    assert "Produção" in previa.content.decode()
    assert confirmacao.status_code == 302
    assert grd.setor == "Produção"
    detalhe = client.get(reverse("grds:detalhe", args=(contrato.pk, grd.pk)))
    assert "Setor de destino" in detalhe.content.decode()
    assert "Produção" in detalhe.content.decode()

    lista_filtrada = client.get(reverse("grds:lista"), {"setor": "Produção"})
    lista_vazia = client.get(reverse("grds:lista"), {"setor": "Qualidade"})
    assert grd.rotulo() in lista_filtrada.content.decode()
    assert grd.rotulo() not in lista_vazia.content.decode()


@pytest.mark.django_db
def test_lista_mestra_mostra_grd_data_em_campo_e_aviso_por_setor(
    contrato, perfil_modelo, equipe
):
    configuracao = garantir_configuracao_grd(contrato)
    configuracao.setores_distribuicao = [
        {"nome": "Produção", "ordem": 1},
        {"nome": "Topografia", "ordem": 2},
        {"nome": "Qualidade", "ordem": 3},
    ]
    configuracao.save(update_fields=("setores_distribuicao",))
    documento = _documento(contrato)
    revisao_1 = _emissao(documento, "1", date(2026, 1, 1))
    revisao_2 = _emissao(documento, "2", date(2026, 2, 1))
    grd_producao = _grd(contrato, 1, date(2026, 1, 2), "Produção")
    grd_topografia = _grd(contrato, 2, date(2026, 2, 2), "Topografia")
    GrdItem.objects.create(grd=grd_producao, emissao=revisao_1)
    GrdItem.objects.create(grd=grd_topografia, emissao=revisao_2)

    dados = carregar_lista_mestra(equipe, contrato.pk)
    linhas = {linha["emissao"].pk: linha for linha in dados["pagina"].object_list}
    linha_1 = linhas[revisao_1.pk]
    linha_2 = linhas[revisao_2.pk]
    producao_1, topografia_1, qualidade_1 = linha_1["distribuicao_setores"]
    producao_2, topografia_2, qualidade_2 = linha_2["distribuicao_setores"]

    assert producao_1["grd_item"].grd == grd_producao
    assert producao_1["data"] == date(2026, 1, 2)
    assert producao_1["em_campo"] == revisao_1
    assert producao_1["desatualizado"] is True
    assert producao_1["revisao_emitida"] == "2"
    assert topografia_1["grd_item"] is None
    assert topografia_1["em_campo"] == revisao_2
    assert topografia_1["desatualizado"] is False
    assert qualidade_1["grd_item"] is None and qualidade_1["em_campo"] is None
    assert producao_2["grd_item"] is None and producao_2["data"] is None
    assert producao_2["em_campo"] == revisao_1
    assert topografia_2["grd_item"].grd == grd_topografia
    assert topografia_2["data"] == date(2026, 2, 2)
    assert topografia_2["em_campo"] == revisao_2
    assert qualidade_2["em_campo"] is None


@pytest.mark.django_db
def test_lista_mestra_colunas_por_setor_nao_faz_consultas_por_documento_ou_setor(
    client, contrato, perfil_modelo, equipe, django_assert_max_num_queries
):
    nomes = ["Produção", "Topografia", "Qualidade", "Comissionamento", "Operação"]
    configuracao = garantir_configuracao_grd(contrato)
    configuracao.setores_distribuicao = [
        {"nome": nome, "ordem": indice}
        for indice, nome in enumerate(nomes, start=1)
    ]
    configuracao.save(update_fields=("setores_distribuicao",))
    emissoes = []
    for indice in range(1, 21):
        codigo = f"DE-15.25.00.00-6A1-{indice:04d}"
        emissoes.append(
            _emissao(
                _documento(contrato, codigo, f"Documento {indice}"),
                "1",
                date(2026, 1, 1),
            )
        )
    for indice, nome in enumerate(nomes, start=1):
        grd = _grd(contrato, indice, date(2026, 1, indice), nome)
        GrdItem.objects.bulk_create(
            [GrdItem(grd=grd, emissao=emissao) for emissao in emissoes]
        )
    client.force_login(equipe)

    with django_assert_max_num_queries(15):
        resposta = client.get(reverse("lista_mestra"), {"contrato": contrato.pk})

    assert resposta.status_code == 200
    assert len(resposta.context["setores_distribuicao"]) == 5
    assert resposta.context["total_filtrado"] == 20
