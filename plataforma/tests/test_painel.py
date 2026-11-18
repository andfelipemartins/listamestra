from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml
from django.contrib.auth.hashers import check_password
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse
from django.utils import timezone

from contratos.admin import ContratoAdminForm
from contratos.models import Contrato, Participacao, PerfilContrato
from documentos.models import Analise, Documento, Emissao
from importacoes.models import (
    ImportacaoID,
    ImportacaoSituacao,
    IndiceDocumentos,
    ItemPrevisto,
)
from painel.servicos import carregar_painel


METRO = Path(__file__).resolve().parents[2] / "core" / "perfil" / "exemplos" / "metro.yaml"


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato de painel",
        codigo_interno="CT-PAINEL",
        cliente="Cliente de teste",
    )


@pytest.fixture
def perfil_modelo(contrato):
    with METRO.open(encoding="utf-8") as arquivo:
        definicao = yaml.safe_load(arquivo)
    definicao["vigencia_inicio"] = (timezone.localdate() - timedelta(days=30)).isoformat()
    return PerfilContrato.objects.create(
        contrato=contrato,
        versao=1,
        vigencia_inicio=timezone.localdate() - timedelta(days=30),
        definicao=definicao,
    )


def _indice(contrato, codigo, *, fonte=IndiceDocumentos.Fonte.EXCEL_ID, revisao="1"):
    return IndiceDocumentos.objects.create(
        contrato=contrato,
        codigo=codigo,
        revisao=revisao,
        fonte=fonte,
        arquivo_nome=f"{codigo}.xlsx",
        importado_em=timezone.now(),
    )


def _documento(contrato, indice, sequencial, classe="P7", situacao=None, *, data=None):
    data = data or timezone.localdate() - timedelta(days=10)
    identificador = f"DOC-{sequencial}"
    documento = Documento.objects.create(
        contrato=contrato,
        identificador_base=identificador,
        tipo="DE",
        trecho="25",
        disciplina=classe,
        titulo=f"Documento {sequencial}",
        atributos={"tipo": "DE", "trecho": "25", "classe": classe, "sequencial": str(sequencial)},
    )
    ItemPrevisto.objects.create(indice=indice, documento=documento, titulo=documento.titulo)
    if situacao is not None:
        emissao = Emissao.objects.create(
            documento=documento,
            revisao="1",
            versao=1,
            fase=Emissao.Fase.PRELIMINAR,
            data_emissao=data,
            origem=Emissao.Origem.CLIENTE,
        )
        Analise.objects.create(
            emissao=emissao,
            etapa="Análise do cliente",
            situacao=situacao,
            origem=Analise.Origem.IMPORTADO_PW,
            data_analise=data + timedelta(days=1),
        )
    return documento


@pytest.mark.django_db
def test_servico_resume_uniao_status_recorte_fonte_e_fora_do_id(contrato, perfil_modelo):
    primeira = _indice(contrato, "ID-A")
    segunda = _indice(contrato, "ID-B")
    _documento(contrato, primeira, 1001, classe="A1")
    _documento(contrato, primeira, 1002, classe="A1", situacao="Em Análise")
    aprovado = _documento(contrato, primeira, 1003, situacao="Aprovado")
    _documento(contrato, primeira, 1004, situacao="Não Aprovado")
    desconhecido = _documento(contrato, primeira, 1005, situacao="Estado Novo do PW")
    ItemPrevisto.objects.create(indice=segunda, documento=aprovado, titulo=aprovado.titulo)
    _documento(contrato, segunda, 1006, classe="P7", situacao="Aprovado")
    fora_id = Documento.objects.create(
        contrato=contrato,
        identificador_base="DOC-FORA-ID",
        atributos={"tipo": "DE", "trecho": "25", "classe": "P7"},
    )
    emissao = Emissao.objects.create(
        documento=fora_id,
        revisao="1",
        versao=1,
        fase=Emissao.Fase.PRELIMINAR,
        data_emissao=timezone.localdate() - timedelta(days=2),
        origem=Emissao.Origem.CLIENTE,
    )
    Analise.objects.create(emissao=emissao, etapa="Análise", situacao="Em Análise")

    data_pw = timezone.localdate() - timedelta(days=1)
    ImportacaoSituacao.objects.create(
        contrato=contrato,
        data_extracao=data_pw,
        arquivo_nome="PW.xlsx",
    )
    importacao_id = ImportacaoID.objects.create(
        contrato=contrato,
        indice=primeira,
        arquivo_nome="ID.xlsx",
    )
    data_id = timezone.localtime(importacao_id.importado_em).date()

    dados = carregar_painel(contrato, "classe")
    resumo = dados["resumo"]

    assert dados["total_documentos_previstos"] == 6
    assert resumo.total_previsto == 6
    assert resumo.contagens["a_emitir"] == 1
    assert resumo.contagens["em_analise"] == 1
    assert resumo.contagens["aprovado"] == 2
    assert resumo.contagens["nao_aprovado"] == 1
    assert resumo.contagens["nao_mapeado"] == 1
    assert resumo.percentual_avanco == pytest.approx(100 / 3)
    assert dados["fora_do_id"] == 1
    assert dados["ultima_situacao_pw"] == data_pw
    assert dados["ultima_importacao_id"] == data_id
    assert dados["por"] == "classe"
    assert any(item["rotulo"] == "Iluminação" for item in dados["recortes"])
    assert any(estado.situacao == "Estado Novo do PW" and estado.contagem == 1 for estado in resumo.estados_nao_mapeados)


@pytest.mark.django_db
def test_servico_usa_analise_mais_recente_da_emissao_mais_recente(contrato, perfil_modelo):
    indice = _indice(contrato, "ID-REVISOES")
    documento = _documento(contrato, indice, 2001)
    emissao_antiga = Emissao.objects.create(
        documento=documento,
        revisao="1",
        versao=1,
        fase=Emissao.Fase.PRELIMINAR,
        data_emissao=timezone.localdate() - timedelta(days=20),
        origem=Emissao.Origem.CLIENTE,
    )
    Analise.objects.create(
        emissao=emissao_antiga,
        etapa="Análise do cliente",
        situacao="Aprovado",
        data_analise=timezone.localdate() - timedelta(days=1),
    )
    emissao_nova = Emissao.objects.create(
        documento=documento,
        revisao="2",
        versao=1,
        fase=Emissao.Fase.PRELIMINAR,
        data_emissao=timezone.localdate() - timedelta(days=5),
        origem=Emissao.Origem.CLIENTE,
    )
    Analise.objects.create(
        emissao=emissao_nova,
        etapa="Análise do cliente",
        situacao="Em Análise",
        data_analise=timezone.localdate() - timedelta(days=4),
    )
    Analise.objects.create(
        emissao=emissao_nova,
        etapa="Análise do cliente",
        situacao="Não Aprovado",
        data_analise=timezone.localdate() - timedelta(days=3),
    )

    resumo = carregar_painel(contrato)["resumo"]

    assert resumo.contagens["nao_aprovado"] == 1
    assert resumo.contagens["aprovado"] == 0


@pytest.mark.django_db
def test_pin_correto_libera_painel_e_pin_errado_nao_libera(client, contrato, perfil_modelo):
    contrato.definir_pin_painel("5724")
    contrato.save(update_fields=("pin_painel",))

    url = reverse("painel", args=(contrato.pk,))
    resposta = client.get(url)
    assert resposta.status_code == 200
    assert "Informe o PIN" in resposta.content.decode()

    resposta = client.post(url, {"pin": "1111"})
    assert resposta.status_code == 200
    assert "PIN incorreto" in resposta.content.decode()
    assert f"painel_liberado_{contrato.pk}" not in client.session

    resposta = client.post(url, {"pin": "5724"})
    assert resposta.status_code == 302
    assert client.session[f"painel_liberado_{contrato.pk}"] is True
    assert client.get(url).status_code == 200


@pytest.mark.django_db
def test_bloqueia_por_cinco_minutos_apos_cinco_pins_errados(client, contrato, perfil_modelo):
    contrato.definir_pin_painel("5724")
    contrato.save(update_fields=("pin_painel",))
    url = reverse("painel", args=(contrato.pk,))

    for tentativa in range(5):
        resposta = client.post(url, {"pin": "0000"})
    assert "bloqueado por 5 minutos" in resposta.content.decode()
    resposta = client.post(url, {"pin": "5724"})
    assert "Muitas tentativas" in resposta.content.decode()
    assert f"painel_liberado_{contrato.pk}" not in client.session


@pytest.mark.django_db
def test_participante_logado_entra_sem_pin(client, contrato, perfil_modelo, django_user_model):
    usuario = django_user_model.objects.create_user(username="chefia", password="senha")
    Participacao.objects.create(usuario=usuario, contrato=contrato, papel="chefia")
    client.force_login(usuario)

    resposta = client.get(reverse("painel", args=(contrato.pk,)))

    assert resposta.status_code == 200
    assert "Documentos previstos" in resposta.content.decode()
    assert f"painel_liberado_{contrato.pk}" not in client.session


@pytest.mark.django_db
def test_troca_recorte_htmx_retorna_somente_fragmento(client, contrato, perfil_modelo, django_user_model):
    usuario = django_user_model.objects.create_user(username="ana", password="senha")
    Participacao.objects.create(usuario=usuario, contrato=contrato, papel="chefia")
    indice = _indice(contrato, "ID-HTMX")
    _documento(contrato, indice, 1001, classe="P7", situacao="Aprovado")
    client.force_login(usuario)

    resposta = client.get(
        reverse("painel_recorte", args=(contrato.pk,)),
        {"por": "classe"},
        HTTP_HX_REQUEST="true",
    )

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Iluminação" in html
    assert "dados-grafico-recortes" in html
    assert "<html" not in html
    assert "Lista Mestra" not in html


@pytest.mark.django_db
def test_admin_grava_pin_em_hash_e_nao_mostra_o_existente(contrato):
    form = ContratoAdminForm(
        data={
            "nome": contrato.nome,
            "codigo_interno": contrato.codigo_interno,
            "cliente": contrato.cliente,
            "descricao": "",
            "ativo": "on",
            "pin_painel": "123456",
        },
        instance=contrato,
    )
    assert form.is_valid(), form.errors
    salvo = form.save()
    assert salvo.pin_painel != "123456"
    assert check_password("123456", salvo.pin_painel)

    form_sem_alteracao = ContratoAdminForm(instance=salvo)
    assert form_sem_alteracao["pin_painel"].value() == ""


@pytest.mark.django_db
def test_comando_demo_recusa_contrato_com_documentos(contrato, perfil_modelo):
    Documento.objects.create(contrato=contrato, identificador_base="EXISTENTE")

    with pytest.raises(CommandError, match="já tenha documentos"):
        call_command("popular_painel_demo", contrato.pk)


@pytest.mark.django_db
def test_comando_demo_cria_somente_dados_sinteticos(contrato, perfil_modelo):
    call_command("popular_painel_demo", contrato.pk)

    assert Documento.objects.filter(contrato=contrato).count() == 63
    assert ItemPrevisto.objects.filter(indice__contrato=contrato, indice__vigente=True).count() == 60
    assert Emissao.objects.filter(documento__contrato=contrato).count() > 0
    assert ImportacaoSituacao.objects.filter(contrato=contrato).exists()
