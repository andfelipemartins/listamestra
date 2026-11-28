from datetime import date, datetime
from pathlib import Path

import pytest
import yaml
from django.contrib import admin
from django.urls import reverse
from django.utils import timezone

from contas.models import Usuario
from contratos.models import Contrato, EscopoContrato, Participacao, PerfilContrato
from documentos.admin import DocumentoAdmin
from documentos.models import Analise, Documento, Emissao, EmpresaElaboradora
from importacoes.models import IndiceDocumentos, ItemPrevisto
from documentos.servicos import editar_titulo_documento


PERFIL_METRO = Path(__file__).resolve().parents[2] / "core" / "perfil" / "exemplos" / "metro.yaml"
CODIGO = "DE-15.25.00.00-6A1-1001"


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato do painel lateral",
        codigo_interno="CT-B088",
        cliente="Cliente de teste",
    )


@pytest.fixture
def perfil_modelo(contrato):
    with PERFIL_METRO.open(encoding="utf-8") as arquivo:
        definicao = _json_compatibility(yaml.safe_load(arquivo))
    definicao["vigencia_inicio"] = "2020-01-01"
    return PerfilContrato.objects.create(
        contrato=contrato,
        versao=1,
        vigencia_inicio=date(2020, 1, 1),
        definicao=definicao,
    )


@pytest.fixture
def usuario_admin(contrato, django_user_model):
    usuario = django_user_model.objects.create_user(
        username="admin-block088",
        password="senha",
        first_name="Ana",
        last_name="Gestora",
    )
    Participacao.objects.create(
        usuario=usuario,
        contrato=contrato,
        papel=Usuario.Perfil.ADMIN,
        ativo=True,
    )
    return usuario


@pytest.fixture
def documento(contrato):
    return Documento.objects.create(
        contrato=contrato,
        identificador_base=CODIGO,
        tipo="DE",
        trecho="25",
        disciplina="A1",
        titulo="Título original",
        atributos={
            "tipo": "DE",
            "linha": "15",
            "trecho": "25",
            "subtrecho": "00",
            "unidade": "00",
            "etapa": "6",
            "classe": "A1",
            "sequencial": "1001",
        },
    )


def _json_compatibility(valor):
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {chave: _json_compatibility(item) for chave, item in valor.items()}
    if isinstance(valor, list):
        return [_json_compatibility(item) for item in valor]
    return valor


@pytest.mark.django_db
def test_painel_usa_as_permissoes_da_pasta(client, contrato, perfil_modelo, documento, usuario_admin, django_user_model):
    client.force_login(usuario_admin)
    url = reverse("documento_painel", args=(contrato.pk, documento.pk))

    resposta_autorizada = client.get(url)

    assert resposta_autorizada.status_code == 200
    assert 'data-painel-raiz' in resposta_autorizada.content.decode()

    externo = django_user_model.objects.create_user(username="externo-block088", password="senha")
    client.force_login(externo)
    client.raise_request_exception = False

    resposta_bloqueada = client.get(url)

    assert resposta_bloqueada.status_code == 403


@pytest.mark.django_db
def test_painel_mostra_segmentos_seus_significados_e_elaborado_por(
    client, contrato, perfil_modelo, documento, usuario_admin
):
    empresa = EmpresaElaboradora.objects.create(contrato=contrato, nome="Projetos Alfa")
    documento.elaborado_por = empresa
    documento.save()
    escopo = EscopoContrato.objects.create(contrato=contrato, nome="Trecho Oratório")
    indice = IndiceDocumentos.objects.create(
        contrato=contrato,
        codigo="ID-B088",
        revisao="1",
        fonte=IndiceDocumentos.Fonte.EXCEL_ID,
        arquivo_nome="ID.xlsx",
        importado_em=timezone.now(),
        importado_por=usuario_admin,
        vigente=True,
    )
    indice.escopos.add(escopo)
    ItemPrevisto.objects.create(indice=indice, documento=documento, titulo=documento.titulo)
    client.force_login(usuario_admin)

    resposta = client.get(reverse("documento_painel", args=(contrato.pk, documento.pk)))
    html = resposta.content.decode()
    partes = resposta.context["partes_codigo"]

    assert resposta.status_code == 200
    assert CODIGO in html
    assert CODIGO.replace(".", "").replace("-", "") in html
    assert "Título original" in html
    assert "Projetos Alfa" in html
    assert "Trecho Oratório" in html
    assert "Contrato do painel lateral" in html
    assert len(partes) > 0
    assert all(parte["rotulo"] in html for parte in partes)
    assert all(parte["significado"] in html for parte in partes)


@pytest.mark.django_db
def test_historico_do_painel_ordena_revisao_e_edicao_do_mais_novo(
    client, contrato, perfil_modelo, documento, usuario_admin
):
    emissao = Emissao.objects.create(
        documento=documento,
        revisao="1",
        fase=Emissao.Fase.PRELIMINAR,
        data_emissao=date(2026, 11, 20),
        origem=Emissao.Origem.CLIENTE,
    )
    analise = Analise.objects.create(
        emissao=emissao,
        etapa="Análise do cliente",
        situacao="Em análise",
        origem=Analise.Origem.IMPORTADO_PW,
        data_analise=date(2026, 11, 21),
    )
    analise.situacao = "Aprovado"
    analise.save()
    editar_titulo_documento(
        usuario_admin,
        contrato.pk,
        documento.pk,
        "Título atualizado",
        "Correção solicitada pela coordenação",
    )
    client.force_login(usuario_admin)

    resposta = client.get(reverse("documento_painel", args=(contrato.pk, documento.pk)))
    html = resposta.content.decode()
    historico_html = html.split('id="documento-painel-conteudo-historico"', maxsplit=1)[1]

    assert resposta.status_code == 200
    assert "Correção solicitada pela coordenação" in historico_html
    assert "Ana Gestora" in historico_html
    assert "Situação: Em análise → Aprovado" in historico_html
    assert "Situação registrada: Em análise" in historico_html
    assert "criou a emissão" in historico_html
    assert historico_html.index("Título atualizado") < historico_html.index("criou a emissão")


@pytest.mark.django_db
def test_lista_mestra_aponta_codigo_para_o_painel(
    client, contrato, perfil_modelo, documento, usuario_admin
):
    Emissao.objects.create(
        documento=documento,
        revisao="1",
        fase=Emissao.Fase.PRELIMINAR,
        data_emissao=date(2026, 11, 20),
        origem=Emissao.Origem.CLIENTE,
    )
    client.force_login(usuario_admin)

    resposta = client.get(reverse("lista_mestra"), {"contrato": contrato.pk})
    html = resposta.content.decode()
    resposta_lista = client.get(reverse("documentos_lista"), {"contrato": contrato.pk})
    html_lista = resposta_lista.content.decode()

    assert resposta.status_code == 200
    assert f'data-painel-url="{reverse("documento_painel", args=(contrato.pk, documento.pk))}"' in html
    assert f'href="{reverse("documento_pasta", args=(contrato.pk, documento.pk))}"' in html
    assert resposta_lista.status_code == 200
    assert f'data-painel-url="{reverse("documento_painel", args=(contrato.pk, documento.pk))}"' in html_lista


@pytest.mark.django_db
def test_admin_documento_mantem_os_dados_em_somente_leitura():
    readonly = set(DocumentoAdmin(Documento, admin.site).get_readonly_fields(None))
    campos_dados = {
        "contrato",
        "identificador_base",
        "titulo",
        "tipo",
        "disciplina",
        "trecho",
        "atributos",
        "elaborado_por",
        "ativo",
        "cancelado_em",
        "cancelado_por",
        "motivo_cancelamento",
        "motivo_cancelamento_obs",
        "observacao_reativacao",
    }

    assert campos_dados <= readonly
    assert "nota_edicao_controlada" in readonly
    assert "Edição controlada" == DocumentoAdmin.nota_edicao_controlada.short_description
