from datetime import date
from pathlib import Path

import pytest
import yaml
from django.urls import reverse
from django.utils import timezone

from contas.models import Usuario
from contratos.models import Contrato, Participacao, PerfilContrato
from documentos.models import Analise, Documento, Emissao
from importacoes.models import IndiceDocumentos, ImportacaoSituacao, ItemPrevisto
from registro.servicos import carregar_eventos


RAIZ = Path(__file__).resolve().parents[2]
PERFIL_METRO = RAIZ / "core" / "perfil" / "exemplos" / "metro.yaml"


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato do block 064",
        codigo_interno="CT-B064",
        cliente="Cliente de teste",
    )


@pytest.fixture
def perfil_modelo(contrato):
    with PERFIL_METRO.open(encoding="utf-8") as arquivo:
        definicao = yaml.safe_load(arquivo)
    definicao["vigencia_inicio"] = "2020-01-01"
    return PerfilContrato.objects.create(
        contrato=contrato,
        versao=1,
        vigencia_inicio=date(2020, 1, 1),
        definicao=definicao,
    )


def _item_id(contrato, codigo, fonte):
    indice = IndiceDocumentos.objects.create(
        contrato=contrato,
        codigo=f"ID-{fonte}",
        revisao="1",
        fonte=fonte,
        arquivo_nome=f"ID-{fonte}.xlsx",
        importado_em=timezone.now(),
    )
    documento = Documento.objects.create(
        contrato=contrato,
        identificador_base=codigo,
        titulo=codigo,
        tipo="DE",
        atributos={"tipo": "DE"},
    )
    ItemPrevisto.objects.create(indice=indice, documento=documento, titulo=documento.titulo)


@pytest.mark.django_db
def test_minha_mesa_mostra_contagens_com_links_quando_compara_id_cliente(
    contrato, perfil_modelo, client, django_user_model
):
    _item_id(contrato, "DOC-FALTA-PW", IndiceDocumentos.Fonte.EXCEL_ID)
    _item_id(contrato, "DOC-FALTA-NOSSO-ID", IndiceDocumentos.Fonte.EXTRACAO_PW)
    usuario = django_user_model.objects.create_user(
        username="b064-comparacao", password="senha", is_staff=True
    )
    client.force_login(usuario)

    resposta = client.get(reverse("inicio"), {"contrato": contrato.pk})

    assert resposta.status_code == 200
    html = resposta.content.decode("utf-8")
    url_pendencias = f'{reverse("acoes:pendencias")}?contrato={contrato.pk}'
    assert f'href="{url_pendencias}">Falta no PW: 1</a>' in html
    assert f'href="{url_pendencias}">Falta no nosso ID: 1</a>' in html


@pytest.mark.django_db
def test_minha_mesa_nao_mostra_contagens_de_id_com_comparacao_desligada(
    contrato, perfil_modelo, client, django_user_model
):
    perfil_modelo.definicao["comparar_id_cliente"] = False
    perfil_modelo.save(update_fields=("definicao",))
    _item_id(contrato, "DOC-FALTA-PW", IndiceDocumentos.Fonte.EXCEL_ID)
    _item_id(contrato, "DOC-FALTA-NOSSO-ID", IndiceDocumentos.Fonte.EXTRACAO_PW)
    usuario = django_user_model.objects.create_user(
        username="b064-sem-comparacao", password="senha", is_staff=True
    )
    client.force_login(usuario)

    resposta = client.get(reverse("inicio"), {"contrato": contrato.pk})

    assert resposta.status_code == 200
    html = resposta.content.decode("utf-8")
    assert "Falta no PW:" not in html
    assert "Falta no nosso ID:" not in html


@pytest.mark.django_db
def test_menu_da_planilha_padrao_aparece_para_admin_e_editor_e_some_para_leitor(
    contrato, client, django_user_model
):
    url_menu = reverse("importar_situacao_padrao")
    url_com_contrato = f"{url_menu}?contrato={contrato.pk}"

    for papel, nome in (
        (Usuario.Perfil.ADMIN, "b064-admin"),
        (Usuario.Perfil.EQUIPE, "b064-editor"),
    ):
        usuario = django_user_model.objects.create_user(username=nome, password="senha")
        Participacao.objects.create(usuario=usuario, contrato=contrato, papel=papel, ativo=True)
        client.force_login(usuario)
        resposta = client.get(reverse("inicio"), {"contrato": contrato.pk})
        html = resposta.content.decode("utf-8")
        assert f'href="{url_com_contrato}"' in html
        assert "Atualizar situação (planilha)" in html

    leitor = django_user_model.objects.create_user(username="b064-leitor", password="senha")
    Participacao.objects.create(
        usuario=leitor,
        contrato=contrato,
        papel=Usuario.Perfil.CHEFIA,
        ativo=True,
    )
    client.force_login(leitor)
    resposta = client.get(reverse("inicio"), {"contrato": contrato.pk})

    html = resposta.content.decode("utf-8")
    assert f'href="{url_com_contrato}"' not in html
    assert "Atualizar situação (planilha)" not in html


@pytest.mark.django_db
def test_atividade_distingue_situacao_pw_e_planilha_padrao(contrato, django_user_model):
    usuario = django_user_model.objects.create_user(username="b064-atividade", password="senha")
    pw = ImportacaoSituacao.objects.create(
        contrato=contrato,
        data_extracao=date(2026, 11, 20),
        arquivo_nome="situacao-pw.xlsx",
        importado_por=usuario,
    )
    planilha = ImportacaoSituacao.objects.create(
        contrato=contrato,
        data_extracao=date(2026, 11, 21),
        arquivo_nome="[Planilha padrão] situacao-equipe.xlsx",
        importado_por=usuario,
    )
    documento = Documento.objects.create(
        contrato=contrato,
        identificador_base="DOC-ATIVIDADE",
        titulo="Documento de atividade",
    )
    emissao = Emissao.objects.create(
        documento=documento,
        revisao="1",
        versao=1,
        fase=Emissao.Fase.PRELIMINAR,
        data_emissao=date(2026, 11, 21),
        origem=Emissao.Origem.CLIENTE,
    )
    analise = Analise(
        emissao=emissao,
        etapa="Análise do cliente",
        situacao="Aprovado",
        origem=Analise.Origem.MANUAL,
        data_analise=date(2026, 11, 21),
        registrado_por=usuario,
    )
    analise._change_reason = f"importacao_situacao_padrao:{planilha.pk}"
    analise.save()

    eventos = carregar_eventos(contrato)
    evento_pw = next(item for item in eventos if item.get("importacao_id") == pw.pk)
    evento_planilha = next(item for item in eventos if item.get("importacao_id") == planilha.pk)

    assert evento_pw["tipo_importacao"] == "situação do PW"
    assert evento_pw["entidade"] == "Importação de situação do PW"
    assert "situação do PW situacao-pw.xlsx" in evento_pw["resumo"]
    assert evento_planilha["tipo_importacao"] == "situação pela planilha padrão"
    assert evento_planilha["entidade"] == "Importação de situação pela planilha padrão"
    assert "situação pela planilha padrão situacao-equipe.xlsx" in evento_planilha["resumo"]
    assert {item["campo"]: item["depois"] for item in evento_planilha["detalhes"]}["Arquivo"] == "situacao-equipe.xlsx"
    assert not any(item.get("entidade") == "análise" for item in eventos)
