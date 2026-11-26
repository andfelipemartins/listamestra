from datetime import timedelta
from pathlib import Path

import pytest
import yaml
from django.utils import timezone

from acoes.models import AcaoPendencia
from acoes.services import (
    PENDENCIA_FALTA_NO_NOSSO_ID,
    PENDENCIA_FALTA_NO_PW,
    carregar_ignorados,
    carregar_minha_mesa,
    reativar_ignorado,
    registrar_acao,
)
from contratos.models import Contrato, PerfilContrato
from documentos.models import Documento
from importacoes.models import IndiceDocumentos, ItemPrevisto
from painel.servicos import carregar_painel


METRO = Path(__file__).resolve().parents[2] / "core" / "perfil" / "exemplos" / "metro.yaml"


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato de comparação de IDs",
        codigo_interno="CT-ID-COMPARACAO",
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


def _indice(contrato, codigo, fonte, *, vigente=True, conta_no_previsto=True, substituido_por=None):
    return IndiceDocumentos.objects.create(
        contrato=contrato,
        codigo=codigo,
        revisao="1",
        conta_no_previsto=conta_no_previsto,
        fonte=fonte,
        arquivo_nome=f"{codigo}.xlsx",
        importado_em=timezone.now(),
        vigente=vigente,
        substituido_por=substituido_por,
    )


def _item(contrato, indice, codigo):
    documento = Documento.objects.create(
        contrato=contrato,
        identificador_base=codigo,
        titulo=f"Título {codigo}",
        tipo="DE",
        atributos={"tipo": "DE", "classe": "P7"},
    )
    ItemPrevisto.objects.create(indice=indice, documento=documento, titulo=documento.titulo)
    return documento


@pytest.mark.django_db
def test_previsto_usa_excel_id_e_extracao_pw_fica_fora_do_total(contrato, perfil_modelo):
    indice_nosso = _indice(contrato, "ID-ALYA", IndiceDocumentos.Fonte.EXCEL_ID)
    indice_pw = _indice(contrato, "ID-PW", IndiceDocumentos.Fonte.EXTRACAO_PW)
    _item(contrato, indice_nosso, "DOC-DO-NOSSO-ID")
    _item(contrato, indice_pw, "DOC-DO-PW")

    dados = carregar_painel(contrato)

    assert dados["total_documentos_previstos"] == 1
    assert dados["quantidade_faltando_id_cliente"] == 1


@pytest.mark.django_db
def test_sem_excel_id_previsto_retorna_ao_fallback_dos_ids_vigentes(contrato, perfil_modelo):
    indice_pw = _indice(contrato, "ID-PW", IndiceDocumentos.Fonte.EXTRACAO_PW)
    _item(contrato, indice_pw, "DOC-DO-PW")

    dados = carregar_painel(contrato)

    assert dados["total_documentos_previstos"] == 1
    assert dados["quantidade_faltando_id_cliente"] == 0


@pytest.mark.django_db
def test_indice_substituido_fica_no_historico_e_nao_entra_no_previsto(contrato, perfil_modelo):
    indice_novo = _indice(contrato, "ID-2001", IndiceDocumentos.Fonte.EXCEL_ID)
    indice_antigo = _indice(
        contrato,
        "ID-1501",
        IndiceDocumentos.Fonte.EXCEL_ID,
        vigente=False,
        substituido_por=indice_novo,
    )
    _item(contrato, indice_antigo, "DOC-HISTORICO")
    _item(contrato, indice_novo, "DOC-VIGENTE")

    dados = carregar_painel(contrato)

    assert dados["total_documentos_previstos"] == 1


@pytest.mark.django_db
def test_pendencias_ao_vivo_registram_pedido_ignoram_e_reativam(
    contrato, perfil_modelo, django_user_model
):
    perfil_modelo.definicao["comparar_id_cliente"] = True
    perfil_modelo.save(update_fields=("definicao",))
    indice_nosso = _indice(contrato, "ID-ALYA", IndiceDocumentos.Fonte.EXCEL_ID)
    indice_pw = _indice(contrato, "ID-PW", IndiceDocumentos.Fonte.EXTRACAO_PW)
    falta_no_pw = _item(contrato, indice_nosso, "DOC-FALTA-NO-PW")
    falta_no_nosso = _item(contrato, indice_pw, "DOC-FALTA-NO-NOSSO-ID")
    cancelado = _item(contrato, indice_pw, "DOC-CANCELADO")
    cancelado.cancelado_em = timezone.now()
    cancelado.save(update_fields=("cancelado_em",))
    usuario = django_user_model.objects.create_user(
        username="admin-id-comparacao",
        password="senha-segura",
        is_staff=True,
    )

    mesa = carregar_minha_mesa(usuario, contrato.pk, limite=None)
    janela = next(item for item in mesa["janelas"] if item["id"] == "erros")
    pendencias = {item["tipo_pendencia"]: item for item in janela["todos"]}

    assert set(pendencias) == {PENDENCIA_FALTA_NO_PW, PENDENCIA_FALTA_NO_NOSSO_ID}
    assert pendencias[PENDENCIA_FALTA_NO_PW]["grupo"] == "Falta no PW"
    assert [item["quantidade"] for item in janela["contagens_pendencias_id"]] == [1, 1]

    pedido = registrar_acao(
        usuario,
        contrato.pk,
        falta_no_pw.pk,
        PENDENCIA_FALTA_NO_PW,
        AcaoPendencia.Acao.PEDIR_CORRECAO,
    )
    assert pedido.acao == AcaoPendencia.Acao.PEDIR_CORRECAO
    assert pedido.usuario == usuario
    assert pedido.criado_em is not None
    assert pedido.texto_email == ""

    ignorada = registrar_acao(
        usuario,
        contrato.pk,
        falta_no_nosso.pk,
        PENDENCIA_FALTA_NO_NOSSO_ID,
        AcaoPendencia.Acao.IGNORAR,
        "Aguardando confirmação do cadastro",
    )
    ignorados = carregar_ignorados(usuario, contrato.pk)
    assert any(
        item["ultima_acao"].pk == ignorada.pk
        for item in ignorados["janela"]["todos"]
    )

    reativar_ignorado(
        usuario,
        contrato.pk,
        falta_no_nosso.pk,
        PENDENCIA_FALTA_NO_NOSSO_ID,
    )
    ignorada.refresh_from_db()
    assert ignorada.resolvida_em is not None
    mesa_reativada = carregar_minha_mesa(usuario, contrato.pk, limite=None)
    janela_reativada = next(item for item in mesa_reativada["janelas"] if item["id"] == "erros")
    assert {item["tipo_pendencia"] for item in janela_reativada["todos"]} == {
        PENDENCIA_FALTA_NO_PW,
        PENDENCIA_FALTA_NO_NOSSO_ID,
    }


@pytest.mark.django_db
def test_comparacao_desligada_nao_cria_pendencias_nem_aviso(
    contrato, perfil_modelo, django_user_model
):
    perfil_modelo.definicao["comparar_id_cliente"] = False
    perfil_modelo.save(update_fields=("definicao",))
    indice_nosso = _indice(contrato, "ID-ALYA", IndiceDocumentos.Fonte.EXCEL_ID)
    indice_pw = _indice(contrato, "ID-PW", IndiceDocumentos.Fonte.EXTRACAO_PW)
    _item(contrato, indice_nosso, "DOC-FALTA-NO-PW")
    _item(contrato, indice_pw, "DOC-FALTA-NO-NOSSO-ID")
    usuario = django_user_model.objects.create_user(
        username="admin-id-desligado",
        password="senha-segura",
        is_staff=True,
    )

    mesa = carregar_minha_mesa(usuario, contrato.pk, limite=None)
    janela = next(item for item in mesa["janelas"] if item["id"] == "erros")
    dados_painel = carregar_painel(contrato)

    assert not any(item["tipo_pendencia"] in {PENDENCIA_FALTA_NO_PW, PENDENCIA_FALTA_NO_NOSSO_ID} for item in janela["todos"])
    assert janela.get("contagens_pendencias_id") is None
    assert dados_painel["quantidade_faltando_id_cliente"] == 0

