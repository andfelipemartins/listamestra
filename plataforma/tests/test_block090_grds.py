from datetime import date, datetime
from pathlib import Path

import pytest
import yaml
from django.urls import reverse

from contas.models import Usuario
from contratos.models import Contrato, Participacao, PerfilContrato
from documentos.models import Documento, Emissao
from grds.models import Grd, GrdCampoCabecalho
from grds.servicos import (
    dados_cabecalho_previa,
    formatar_numero_grd,
    garantir_configuracao_grd,
    preparar_grd,
)


PERFIL_METRO = Path(__file__).resolve().parents[2] / "core" / "perfil" / "exemplos" / "metro.yaml"
CODIGO_1 = "DE-15.25.00.00-6A1-1001"
CODIGO_2 = "DE-15.25.02.00-6A1-1002"


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Estação São Mateus",
        codigo_interno="CT-B090",
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


def _json_compatibility(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_compatibility(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_compatibility(item) for item in value]
    return value


@pytest.fixture
def admin_contrato(contrato, django_user_model):
    usuario = django_user_model.objects.create_user(
        username="admin-b090",
        password="senha",
        first_name="Érica",
        last_name="Engenheira Civil",
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
        username="equipe-b090", password="senha", first_name="Ester"
    )
    Participacao.objects.create(
        usuario=usuario,
        contrato=contrato,
        papel=Usuario.Perfil.EQUIPE,
        ativo=True,
    )
    return usuario


@pytest.fixture
def emissoes(contrato, perfil_modelo):
    resultado = []
    for codigo, titulo in ((CODIGO_1, "Planta geral"), (CODIGO_2, "Planta de detalhe")):
        documento = Documento.objects.create(
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
                "subtrecho": codigo.split("-")[1].split(".")[2],
                "unidade": "00",
                "etapa": "6",
                "classe": "A1",
                "sequencial": codigo[-4:],
            },
        )
        resultado.append(
            Emissao.objects.create(
                documento=documento,
                revisao="A",
                versao=1,
                fase=Emissao.Fase.ORIGINAL,
                data_emissao=date(2026, 10, 10),
                origem=Emissao.Origem.INTERNA,
            )
        )
    return resultado


@pytest.mark.django_db
def test_configuracao_padrao_e_trecho_unico(contrato, perfil_modelo, emissoes):
    configuracao = garantir_configuracao_grd(contrato)
    assert configuracao.formato_numero == "{sigla} {seq:03d}/{ano}"
    assert configuracao.nome_emitente == "ÁLYA"
    assert configuracao.formatos_copias == ["A1", "A3", "A4", "Digital"]
    assert list(configuracao.campos.values_list("chave", flat=True)) == [
        "obra",
        "trecho",
        "ac",
    ]
    trecho = configuracao.campos.get(chave="trecho")
    assert trecho.segmentos_codigo == ["linha", "trecho", "subtrecho", "unidade"]

    previa = preparar_grd(contrato, f"{CODIGO_1}\n{CODIGO_1}\n{CODIGO_2}")
    cabecalho = dados_cabecalho_previa(
        contrato, previa, date(2026, 11, 28), {str(configuracao.campos.get(chave="ac").pk): "Eng. Ana"}
    )

    campo_trecho = next(campo for campo in cabecalho["campos"] if campo["rotulo"] == "Trecho")
    campo_ac = next(campo for campo in cabecalho["campos"] if campo["rotulo"] == "A/C")
    assert campo_trecho["valor"] == "15.25.00.00 / 15.25.02.00"
    assert campo_ac["valor"] == "Eng. Ana"
    assert cabecalho["numero_formatado"] == "ÁLYA 001/2026"
    configuracao.formato_numero = "{sigla}-{seq:04d}-{ano}"
    assert formatar_numero_grd(configuracao, 8, date(2025, 1, 1)) == "ÁLYA-0008-2025"


@pytest.mark.django_db
def test_admin_configura_numero_e_desativa_campo(
    client, contrato, admin_contrato
):
    configuracao = garantir_configuracao_grd(contrato)
    configuracao.formato_numero = "{sigla}-{seq:04d}-{ano}"
    configuracao.save()
    request = client
    request.force_login(admin_contrato)
    session = request.session
    session["contrato_ativo_id"] = contrato.pk
    session.save()

    pagina = request.get(reverse("grds:configurar"))
    formset = pagina.context["formset"]
    dados = {
        "nome_emitente": "Consórcio L15",
        "titulo": "Guia de Remessa",
        "formato_numero": "{sigla}-{seq:04d}-{ano}",
        "formatos_copias": ["A1", "Digital"],
        f"{formset.prefix}-TOTAL_FORMS": str(len(formset.forms)),
        f"{formset.prefix}-INITIAL_FORMS": str(formset.initial_form_count()),
        f"{formset.prefix}-MIN_NUM_FORMS": "0",
        f"{formset.prefix}-MAX_NUM_FORMS": "10",
    }
    for indice, form in enumerate(formset.forms):
        campo = form.instance
        prefixo = f"{formset.prefix}-{indice}"
        if campo.pk:
            dados[f"{prefixo}-id"] = str(campo.pk)
        dados[f"{prefixo}-chave"] = campo.chave
        dados[f"{prefixo}-rotulo"] = campo.rotulo
        dados[f"{prefixo}-fonte"] = campo.fonte
        dados[f"{prefixo}-valor_contrato"] = campo.valor_contrato
        dados[f"{prefixo}-ordem"] = str(campo.ordem)
        if campo.habilitado and campo.chave != "trecho":
            dados[f"{prefixo}-habilitado"] = "on"
        for segmento in (campo.segmentos_codigo or []):
            dados[f"{prefixo}-segmentos_codigo"] = dados.get(
                f"{prefixo}-segmentos_codigo", []
            ) + [segmento]

    resposta = request.post(reverse("grds:configurar"), dados)

    assert resposta.status_code == 302
    configuracao.refresh_from_db()
    assert configuracao.nome_emitente == "Consórcio L15"
    assert configuracao.formato_numero == "{sigla}-{seq:04d}-{ano}"
    assert configuracao.formatos_copias == ["A1", "Digital"]
    assert not configuracao.campos.get(chave="trecho").habilitado


@pytest.mark.django_db
def test_criacao_impressa_usa_digitado_copias_e_nome_completo(
    client, contrato, perfil_modelo, emissoes, admin_contrato
):
    configuracao = garantir_configuracao_grd(contrato)
    configuracao.formatos_copias = ["A1", "Digital"]
    configuracao.save()
    modulo = GrdCampoCabecalho.objects.create(
        configuracao=configuracao,
        chave="modulo",
        habilitado=False,
        rotulo="Módulo",
        fonte=GrdCampoCabecalho.Fonte.CONTRATO,
        valor_contrato="Não deve aparecer",
        ordem=40,
    )
    client.force_login(admin_contrato)
    session = client.session
    session["contrato_ativo_id"] = contrato.pk
    session.save()
    url_nova = reverse("grds:nova")
    campos = list(
        configuracao.campos.filter(
            habilitado=True, fonte=GrdCampoCabecalho.Fonte.DIGITADO
        )
    )
    ac = campos[0]
    dados = {
        "contrato": contrato.pk,
        "data": "2026-11-28",
        "destinatario": "Cliente",
        "observacao": "",
        "texto_codigos": f"{CODIGO_1}\n{CODIGO_2}",
        f"campo_{ac.pk}": "Eng. Paula",
        "etapa": "previa",
    }

    previa = client.post(url_nova, dados)

    assert previa.status_code == 200
    assert "Eng. Paula" in previa.content.decode()
    assert "15.25.00.00 / 15.25.02.00" in previa.content.decode()
    assert "Não deve aparecer" not in previa.content.decode()
    assert 'name="qtd_' in previa.content.decode()
    assert ">A3<" not in previa.content.decode()

    dados.update(
        {
            "etapa": "confirmar",
            f"qtd_{emissoes[0].pk}_A1": "2",
            f"qtd_{emissoes[1].pk}_A1": "0",
        }
    )
    confirmacao = client.post(url_nova, dados)
    grd = Grd.objects.get(contrato=contrato)

    assert confirmacao.status_code == 302
    assert grd.rotulo() == "ÁLYA 001/2026"
    assert grd.itens.get(emissao=emissoes[0]).copias == {"A1": 2, "Digital": 1}
    assert grd.emitido_por_nome == "Érica Engenheira Civil"
    detalhe = client.get(reverse("grds:detalhe", args=(contrato.pk, grd.pk)))
    html = detalhe.content.decode()
    assert "Érica Engenheira Civil" in html
    assert "Eng. Paula" in html
    assert "Digital" in html and "A1" in html
    assert "Não deve aparecer" not in html
    assert "Módulo" not in html
    assert "Recebido por" in html and "Emitido por" in html


@pytest.mark.django_db
def test_configuracao_exige_staff_ou_admin_e_contrato_ativo(
    client, contrato, equipe, django_user_model
):
    client.force_login(equipe)
    session = client.session
    session["contrato_ativo_id"] = contrato.pk
    session.save()
    assert client.get(reverse("grds:configurar")).status_code == 403

    staff = django_user_model.objects.create_user(
        username="staff-b090", password="senha", is_staff=True
    )
    client.force_login(staff)
    session = client.session
    session.pop("contrato_ativo_id", None)
    session.save()
    assert client.get(reverse("grds:configurar")).url == reverse("contratos_escolher")
