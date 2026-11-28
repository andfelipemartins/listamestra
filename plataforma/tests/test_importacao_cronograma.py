from datetime import date, datetime
from io import BytesIO, StringIO
from pathlib import Path

import pytest
import yaml
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from openpyxl import Workbook

from core.perfil import perfil_de_dict
from contratos.models import Contrato, PerfilContrato
from documentos.models import Documento, Emissao
from importacoes.cronograma import (
    aplicar_previa_cronograma,
    comparar_previsoes_cronograma,
    gerar_previa_cronograma,
)
from importacoes.models import (
    ImportacaoCronograma,
    IndiceDocumentos,
    ItemPrevisto,
    PrevisaoEmissao,
)
from tests.importacoes_helpers import ativar_contrato


RAIZ_REPOSITORIO = Path(__file__).resolve().parents[2]
PERFIL_METRO = RAIZ_REPOSITORIO / "core" / "perfil" / "exemplos" / "metro.yaml"
HOJE = date(2026, 11, 19)


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato de cronograma",
        codigo_interno="CT-CRONO",
        cliente="Cliente de teste",
    )


@pytest.fixture
def perfil_modelo(contrato):
    with PERFIL_METRO.open(encoding="utf-8") as arquivo:
        definicao = _json_compatibility(yaml.safe_load(arquivo))
    return PerfilContrato.objects.create(
        contrato=contrato,
        versao=1,
        vigencia_inicio=date(2026, 1, 1),
        definicao=definicao,
    )


def _json_compatibility(valor):
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {chave: _json_compatibility(item) for chave, item in valor.items()}
    if isinstance(valor, list):
        return [_json_compatibility(item) for item in valor]
    return valor


def _codigo(sequencial):
    return f"DE-15.25.00.00-6A1-{sequencial}"


def _criar_previsto(contrato, perfil_modelo, sequencial):
    identificador = perfil_de_dict(perfil_modelo.definicao)
    from core.perfil.codigo import interpretar

    interpretado = interpretar(identificador, _codigo(sequencial))
    documento = Documento.objects.create(
        contrato=contrato,
        identificador_base=interpretado.identificador_base,
        titulo=f"Documento {sequencial}",
    )
    indice, _ = IndiceDocumentos.objects.get_or_create(
        contrato=contrato,
        codigo="ID-CRONOGRAMA",
        revisao="1",
        fonte=IndiceDocumentos.Fonte.EXCEL_ID,
        defaults={
            "arquivo_nome": "ID.xlsx",
            "importado_em": timezone.make_aware(datetime(2026, 1, 1)),
            "vigente": True,
        },
    )
    ItemPrevisto.objects.create(indice=indice, documento=documento)
    return documento


def _xlsx(linhas, cabecalhos=None):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(cabecalhos or ["Código", "Revisão", "Versão", "Data prevista"])
    for linha in linhas:
        worksheet.append(linha)
    arquivo = BytesIO()
    workbook.save(arquivo)
    arquivo.seek(0)
    return arquivo


def _previa(arquivo, nome, contrato, perfil_modelo):
    return gerar_previa_cronograma(
        arquivo,
        nome_arquivo=nome,
        contrato_id=contrato.pk,
        perfil_id=perfil_modelo.pk,
        perfil=perfil_de_dict(perfil_modelo.definicao),
        documentos_previstos=ItemPrevisto.objects.filter(
            indice__contrato=contrato,
            indice__vigente=True,
            excluido=False,
        ).values_list("documento__identificador_base", flat=True),
    )


@pytest.mark.django_db
def test_importa_previsao_xlsx_com_revisao_e_versao_ignoradas(contrato, perfil_modelo):
    documento = _criar_previsto(contrato, perfil_modelo, "1001")
    previa = _previa(
        _xlsx([[_codigo("1001"), "A1", 2, datetime(2026, 12, 5)]]),
        "cronograma.xlsx",
        contrato,
        perfil_modelo,
    )

    assert previa.linhas_validas == 1
    assert previa.linhas[0].data_prevista == date(2026, 12, 5)
    importacao = aplicar_previa_cronograma(
        previa,
        contrato=contrato,
        perfil_modelo=perfil_modelo,
    )

    previsao = PrevisaoEmissao.objects.get(contrato=contrato, documento=documento)
    assert importacao.linhas_validas == 1
    assert previsao.data_prevista == date(2026, 12, 5)
    assert previsao.importacao == importacao


@pytest.mark.django_db
def test_recusa_codigo_invalido(contrato, perfil_modelo):
    _criar_previsto(contrato, perfil_modelo, "1001")
    previa = _previa(
        _xlsx([["DE-15.25.00.00-6A1-10X1", "1", 1, "05/12/2026"]]),
        "cronograma.xlsx",
        contrato,
        perfil_modelo,
    )

    assert previa.linhas_validas == 0
    assert previa.linhas_recusadas == 1
    assert previa.linhas[0].categoria == "codigos_invalidos"
    assert previa.linhas[0].mensagem.startswith("Código inválido:")


@pytest.mark.django_db
def test_recusa_documento_fora_do_id(contrato, perfil_modelo):
    previa = _previa(
        _xlsx([[_codigo("1002"), "1", 1, "05/12/2026"]]),
        "cronograma.xlsx",
        contrato,
        perfil_modelo,
    )

    assert previa.linhas_validas == 0
    assert previa.linhas[0].categoria == "fora_do_id"
    assert "não consta no ID" in previa.linhas[0].mensagem


@pytest.mark.django_db
def test_reimportacao_substitui_data_e_importacao_de_origem(contrato, perfil_modelo):
    documento = _criar_previsto(contrato, perfil_modelo, "1001")
    primeira = _previa(
        _xlsx([[_codigo("1001"), "1", 1, "05/12/2026"]]),
        "cronograma-a.csv.xlsx",
        contrato,
        perfil_modelo,
    )
    importacao_a = aplicar_previa_cronograma(primeira, contrato=contrato, perfil_modelo=perfil_modelo)
    previsao = PrevisaoEmissao.objects.get(documento=documento)
    primeira_pk = previsao.pk

    segunda = _previa(
        _xlsx([[_codigo("1001"), "2", 1, "15/12/2026"]]),
        "cronograma-b.xlsx",
        contrato,
        perfil_modelo,
    )
    importacao_b = aplicar_previa_cronograma(segunda, contrato=contrato, perfil_modelo=perfil_modelo)
    previsao.refresh_from_db()

    assert ImportacaoCronograma.objects.count() == 2
    assert PrevisaoEmissao.objects.filter(contrato=contrato, documento=documento).count() == 1
    assert previsao.pk == primeira_pk
    assert previsao.data_prevista == date(2026, 12, 15)
    assert previsao.importacao == importacao_b
    assert importacao_a != importacao_b
    assert previsao.history.count() == 2


@pytest.mark.django_db
def test_compara_previsao_com_primeira_emissao_real(contrato, perfil_modelo):
    documentos = [_criar_previsto(contrato, perfil_modelo, str(1101 + indice)) for indice in range(4)]
    linhas = [
        [_codigo("1101"), "1", 1, date(2026, 11, 20)],
        [_codigo("1102"), "1", 1, date(2026, 11, 20)],
        [_codigo("1103"), "1", 1, date(2026, 11, 18)],
        [_codigo("1104"), "1", 1, date(2026, 11, 20)],
    ]
    previa = _previa(_xlsx(linhas), "cronograma.xlsx", contrato, perfil_modelo)
    aplicar_previa_cronograma(previa, contrato=contrato, perfil_modelo=perfil_modelo)
    Emissao.objects.create(
        documento=documentos[0], revisao="1", versao=2,
        fase=Emissao.Fase.PRELIMINAR, data_emissao=date(2026, 11, 18),
        origem=Emissao.Origem.INTERNA,
    )
    Emissao.objects.create(
        documento=documentos[0], revisao="1", versao=1,
        fase=Emissao.Fase.PRELIMINAR, data_emissao=date(2026, 11, 19),
        origem=Emissao.Origem.CLIENTE,
    )
    Emissao.objects.create(
        documento=documentos[1], revisao="1", versao=1,
        fase=Emissao.Fase.PRELIMINAR, data_emissao=date(2026, 11, 21),
        origem=Emissao.Origem.CLIENTE,
    )
    Emissao.objects.create(
        documento=documentos[1], revisao="2", versao=1,
        fase=Emissao.Fase.PRELIMINAR, data_emissao=date(2026, 11, 22),
        origem=Emissao.Origem.CLIENTE,
    )

    resultados = comparar_previsoes_cronograma(contrato, hoje=HOJE)
    por_codigo = {resultado.previsao.documento.identificador_base[-4:]: resultado for resultado in resultados}

    assert por_codigo["1101"].status == "no_prazo"
    assert por_codigo["1101"].data_real == date(2026, 11, 19)
    assert por_codigo["1102"].status == "atrasado"
    assert por_codigo["1102"].data_real == date(2026, 11, 21)
    assert por_codigo["1103"].status == "vencido_sem_emissao"
    assert por_codigo["1103"].data_real is None
    assert por_codigo["1104"].status == "futuro"
    assert por_codigo["1104"].data_real is None


@pytest.mark.django_db
def test_le_csv_com_cabecalho_por_nome(contrato, perfil_modelo):
    _criar_previsto(contrato, perfil_modelo, "1001")
    arquivo = StringIO("Código;Previsão;Revisão\n" + _codigo("1001") + ";19/12/2026;A1\n")
    previa = _previa(arquivo, "cronograma.csv", contrato, perfil_modelo)

    assert previa.linhas_validas == 1
    assert previa.linhas[0].data_prevista == date(2026, 12, 19)


@pytest.mark.django_db
def test_tela_exibe_previa_e_confirma_importacao(client, contrato, perfil_modelo, django_user_model):
    documento = _criar_previsto(contrato, perfil_modelo, "1001")
    administrador = django_user_model.objects.create_superuser(
        username="admin-cronograma",
        email="admin-cronograma@example.com",
        password="senha-segura",
    )
    client.force_login(administrador)
    ativar_contrato(client, contrato)
    planilha = _xlsx([[_codigo("1001"), "1", 1, "19/12/2026"]])
    upload = SimpleUploadedFile(
        "cronograma.xlsx",
        planilha.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    previa = client.post(
        reverse("importar_cronograma"),
        {"acao": "prever", "arquivo": upload},
        HTTP_HX_REQUEST="true",
    )
    assert previa.status_code == 200
    assert "19/12/2026" in previa.content.decode()
    assert not PrevisaoEmissao.objects.filter(documento=documento).exists()

    resposta = client.post(reverse("importar_cronograma"), {"acao": "confirmar"}, follow=True)

    assert resposta.status_code == 200
    assert "1 previsões atualizadas" in resposta.content.decode()
    assert PrevisaoEmissao.objects.get(documento=documento).data_prevista == date(2026, 12, 19)
