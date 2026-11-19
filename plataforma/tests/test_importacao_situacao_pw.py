from datetime import date, datetime
from io import BytesIO
from pathlib import Path

import pytest
import yaml
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import Workbook

from core.perfil import perfil_de_dict
from contratos.models import Contrato, PerfilContrato
from documentos.models import Analise, Documento, Emissao
from importacoes.models import ImportacaoSituacao, InconsistenciaImportacao, ItemPrevisto
from importacoes.situacao_pw import aplicar_previa_situacao_pw, gerar_previa_situacao_pw
from registro.servicos import carregar_eventos


ROOT = Path(__file__).resolve().parents[2]
METRO = ROOT / "core" / "perfil" / "exemplos" / "metro.yaml"
HEADERS = [
    "Document Type Hierarchy - Document Type",
    "Document Type Hierarchy - Document Subtype",
    "Location Hierarchy - Location",
    "Location Hierarchy - Sublocation",
    "Discipline Hierarchy - Discipline",
    "Discipline Hierarchy - Subdiscipline",
    "Classe",
    "Sequencial",
    "Revisão",
    "Version",
    "Current State Name",
    "Data Real da Emissão",
    "Data Resposta",
    "Título",
    "Código Base",
    "File Name",
    "Histórico do Workflow",
]


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato sintético",
        codigo_interno="CT-PW-SINT",
        cliente="Cliente sintético",
    )


@pytest.fixture
def perfil_modelo(contrato):
    with METRO.open(encoding="utf-8") as arquivo:
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


def _linha(codigo, revisao, versao, situacao, emissao, historico, *, resposta="<Empty Value>", titulo="Título sintético"):
    return {
        "Document Type Hierarchy - Document Type": "DE",
        "Document Type Hierarchy - Document Subtype": "15",
        "Location Hierarchy - Location": "25",
        "Location Hierarchy - Sublocation": "00",
        "Discipline Hierarchy - Discipline": "00",
        "Discipline Hierarchy - Subdiscipline": "6",
        "Classe": "A1",
        "Sequencial": codigo[-4:],
        "Revisão": revisao,
        "Version": versao,
        "Current State Name": situacao,
        "Data Real da Emissão": emissao,
        "Data Resposta": resposta,
        "Título": titulo,
        "Código Base": codigo,
        "File Name": f"{codigo}-{revisao}.pdf",
        "Histórico do Workflow": historico,
    }


def criar_excel_pw(linhas, *, filtros=True):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Export"
    if filtros:
        worksheet.append(["Applied filters: Status = all"])
    worksheet.append(HEADERS)
    for linha in linhas:
        worksheet.append([linha.get(cabecalho) for cabecalho in HEADERS])
    conteudo = BytesIO()
    workbook.save(conteudo)
    conteudo.seek(0)
    return conteudo


def previa_para(arquivo, contrato, perfil_modelo, **kwargs):
    return gerar_previa_situacao_pw(
        arquivo,
        nome_arquivo="PW-sintetico.xlsx",
        contrato_id=contrato.pk,
        perfil_id=perfil_modelo.pk,
        perfil=perfil_de_dict(perfil_modelo.definicao),
        data_extracao=date(2026, 11, 18),
        **kwargs,
    )


@pytest.mark.django_db
def test_ciclo_1_2_3_0_deduz_nao_aprovado_e_aprovado(contrato, perfil_modelo):
    codigo = "DE-15.25.00.00-6A1-1001"
    historico = ", ".join(
        [
            "28/02/2025 - (1.1) Em Análise",
            "25/03/2025 - (1.1) Revisão Superada",
            "20/04/2025 - (2.1) Em Análise",
            "22/05/2025 - (2.1) Revisão Superada",
            "10/06/2025 - (3.1) Em Análise",
            "12/07/2025 - (3.1) Revisão Superada",
            "20/08/2025 - (0.1) Aprovado",
        ]
    )
    linhas = [
        _linha(codigo, "1", 1, "Revisão Superada", "01/02/2025", historico),
        _linha(codigo, "2", 1, "Revisão Superada", "01/04/2025", historico),
        _linha(codigo, "3", 1, "Revisão Superada", "01/06/2025", historico),
        _linha(codigo, "0", 1, "Aprovado", "01/08/2025", historico, resposta="20/08/2025"),
    ]

    previa = previa_para(criar_excel_pw(linhas), contrato, perfil_modelo)
    emissao_por_revisao = {emissao.revisao: emissao for emissao in previa.documentos[0].emissoes}

    assert len(previa.documentos) == 1
    assert previa.emissoes_novas == 4
    assert next(a for a in emissao_por_revisao["1"].analises if a.origem == "deduzido_pw").situacao == "Não Aprovado"
    assert next(a for a in emissao_por_revisao["2"].analises if a.origem == "deduzido_pw").situacao == "Não Aprovado"
    assert next(a for a in emissao_por_revisao["3"].analises if a.origem == "deduzido_pw").situacao == "Aprovado"


@pytest.mark.django_db
def test_nova_versao_deduz_inconsistente(contrato, perfil_modelo):
    codigo = "DE-15.25.00.00-6A1-1002"
    historico = "28/02/2025 - (1.1) Em Análise, 25/03/2025 - (1.1) Revisão Superada, 20/04/2025 - (1.2) Inconsistente"
    linhas = [
        _linha(codigo, "1", 1, "Revisão Superada", "01/02/2025", historico),
        _linha(codigo, "1", 2, "Inconsistente", "01/04/2025", historico, resposta="20/04/2025"),
    ]

    previa = previa_para(criar_excel_pw(linhas), contrato, perfil_modelo)
    emissao = next(item for item in previa.documentos[0].emissoes if item.versao == 1)

    assert next(a for a in emissao.analises if a.origem == "deduzido_pw").situacao == "Inconsistente"


@pytest.mark.django_db
def test_reabertura_a1_para_a_deduz_aprovado(contrato, perfil_modelo):
    codigo = "DE-15.25.00.00-6A1-1003"
    historico = "28/02/2025 - (A.1) Em Análise, 25/03/2025 - (A.1) Revisão Superada, 20/04/2025 - (A.1) Aprovado"
    linhas = [
        _linha(codigo, "A1", 1, "Revisão Superada", "01/02/2025", historico),
        _linha(codigo, "A", 1, "Aprovado", "01/04/2025", historico, resposta="20/04/2025"),
    ]

    previa = previa_para(criar_excel_pw(linhas), contrato, perfil_modelo)
    emissao = next(item for item in previa.documentos[0].emissoes if item.revisao == "A1")

    assert next(a for a in emissao.analises if a.origem == "deduzido_pw").situacao == "Aprovado"


@pytest.mark.django_db
def test_ignora_filtros_descarta_item_truncado_e_separa_fora_do_id(contrato, perfil_modelo):
    codigo = "DE-15.25.00.00-6A1-1004"
    linha = _linha(
        codigo,
        "A1",
        1,
        "Em Análise",
        "01/02/2025",
        "28/02/2025 - (A1.1) Em Análise, 10/03/2025 - (A.1) Em An",
    )

    previa = previa_para(
        criar_excel_pw([linha]),
        contrato,
        perfil_modelo,
        identificadores_previstos=(),
    )

    assert len(previa.documentos) == 1
    assert previa.documentos[0].fora_do_id
    assert previa.documentos_fora_do_id == 1
    assert len(previa.historicos_truncados) == 1
    assert "Em An" in previa.historicos_truncados[0].trecho_descartado
    assert all(a.situacao != "Em An" for a in previa.documentos[0].emissoes[0].analises)


@pytest.mark.django_db
def test_codigo_invalido_fica_na_previa_sem_bloquear_validos(contrato, perfil_modelo):
    bom = "DE-15.25.00.00-6A1-1005"
    linhas = [
        _linha(bom, "1", 1, "Em Análise", "01/02/2025", "28/02/2025 - (1.1) Em Análise"),
        _linha("CODIGO-INVALIDO", "1", 1, "Em Análise", "01/02/2025", ""),
    ]

    previa = previa_para(criar_excel_pw(linhas), contrato, perfil_modelo)

    assert len(previa.documentos) == 1
    assert len(previa.linhas_invalidas) == 1
    assert previa.linhas_invalidas[0].codigo == "CODIGO-INVALIDO"


@pytest.mark.django_db
def test_importacao_idempotente_registra_extracao_e_nao_duplica(contrato, perfil_modelo):
    codigo = "DE-15.25.00.00-6A1-1006"
    linha = _linha(codigo, "1", 1, "Em Análise", "01/02/2025", "28/02/2025 - (1.1) Em Análise")
    arquivo = criar_excel_pw([linha])
    previa = previa_para(arquivo, contrato, perfil_modelo)

    primeira = aplicar_previa_situacao_pw(previa, contrato=contrato, perfil_modelo=perfil_modelo)
    eventos_do_codigo = [
        evento for evento in carregar_eventos(contrato)
        if codigo in evento["codigo"]
    ]
    assert len(eventos_do_codigo) == 1
    assert eventos_do_codigo[0]["acao"] == "importou"
    detalhe_importado = {
        item["campo"]: item["depois"]
        for item in eventos_do_codigo[0]["detalhes"]
    }
    assert "criou 1 documento" in detalhe_importado["Alterações agrupadas"]
    assert "criou 1 emissão" in detalhe_importado["Alterações agrupadas"]
    assert "criou 1 análise" in detalhe_importado["Alterações agrupadas"]
    repetir = previa_para(criar_excel_pw([linha]), contrato, perfil_modelo)
    segunda = aplicar_previa_situacao_pw(repetir, contrato=contrato, perfil_modelo=perfil_modelo)

    assert primeira.data_extracao == date(2026, 11, 18)
    assert segunda.data_extracao == date(2026, 11, 18)
    assert Documento.objects.filter(contrato=contrato).count() == 1
    assert Emissao.objects.filter(documento__contrato=contrato).count() == 1
    assert Analise.objects.filter(emissao__documento__contrato=contrato).count() == 1
    assert ImportacaoSituacao.objects.filter(contrato=contrato).count() == 2


@pytest.mark.django_db
def test_reimportar_preserva_analise_deduzida_sem_historico_extra(contrato, perfil_modelo):
    codigo = "DE-15.25.00.00-6A1-1010"
    historico = "28/02/2025 - (1.1) Em Análise, 25/03/2025 - (1.1) Revisão Superada, 20/04/2025 - (1.2) Inconsistente"
    linhas = [
        _linha(codigo, "1", 1, "Revisão Superada", "01/02/2025", historico),
        _linha(codigo, "1", 2, "Inconsistente", "01/04/2025", historico, resposta="20/04/2025"),
    ]
    aplicar_previa_situacao_pw(
        previa_para(criar_excel_pw(linhas), contrato, perfil_modelo),
        contrato=contrato,
        perfil_modelo=perfil_modelo,
    )
    historico_apos_primeira = Analise.history.count()

    aplicar_previa_situacao_pw(
        previa_para(criar_excel_pw(linhas), contrato, perfil_modelo),
        contrato=contrato,
        perfil_modelo=perfil_modelo,
    )

    assert Analise.objects.filter(emissao__documento__contrato=contrato).count() == 3
    assert Analise.history.count() == historico_apos_primeira


@pytest.mark.django_db
def test_documento_fora_do_id_tem_marca_e_codigo_invalido_vira_inconsistencia(contrato, perfil_modelo):
    codigo = "DE-15.25.00.00-6A1-1007"
    linhas = [
        _linha(codigo, "1", 1, "Em Análise", "01/02/2025", ""),
        _linha("CODIGO-INVALIDO", "1", 1, "Em Análise", "01/02/2025", ""),
    ]
    previa = previa_para(criar_excel_pw(linhas), contrato, perfil_modelo)

    importacao = aplicar_previa_situacao_pw(previa, contrato=contrato, perfil_modelo=perfil_modelo)

    documento = Documento.objects.get(contrato=contrato)
    assert documento.fora_do_id
    assert importacao.fora_do_id == 2
    assert InconsistenciaImportacao.objects.filter(importacao_situacao=importacao).count() == 1
    assert importacao.inconsistencias.get().caixa_falhou


@pytest.mark.django_db
def test_tela_staff_preve_e_confirma_importacao_pw(client, contrato, perfil_modelo, django_user_model):
    administrador = django_user_model.objects.create_superuser(
        username="admin-pw-sintetico",
        email="admin-pw-sintetico@example.com",
        password="senha-segura",
    )
    client.force_login(administrador)
    codigo = "DE-15.25.00.00-6A1-1008"
    arquivo = criar_excel_pw(
        [_linha(codigo, "1", 1, "Em Análise", "01/02/2025", "28/02/2025 - (1.1) Em Análise")]
    )
    upload = SimpleUploadedFile(
        "situacao-sintetica.xlsx",
        arquivo.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    resposta = client.post(
        reverse("importar_situacao_pw"),
        {
            "acao": "prever",
            "contrato": str(contrato.pk),
            "data_extracao": "2026-11-18",
            "arquivo": upload,
        },
    )

    assert resposta.status_code == 200
    assert b"situacao-sintetica.xlsx" in resposta.content
    assert b"Importar dados v\xc3\xa1lidos" in resposta.content
    assert Documento.objects.filter(contrato=contrato).count() == 0

    resposta = client.post(reverse("importar_situacao_pw"), {"acao": "confirmar"}, follow=True)

    assert resposta.status_code == 200
    assert b"1 emiss\xc3\xb5es novas" in resposta.content
    assert Documento.objects.filter(contrato=contrato, fora_do_id=True).count() == 1
    assert ImportacaoSituacao.objects.filter(contrato=contrato).count() == 1
    assert Analise.objects.filter(emissao__documento__contrato=contrato).count() == 1


@pytest.mark.django_db
def test_reprocessa_recusa_situacao_com_perfil_vigente_e_resolve(contrato, perfil_modelo, client, django_user_model):
    definicao_antiga = _json_compatibility(yaml.safe_load(METRO.read_text(encoding="utf-8")))
    definicao_metro = _json_compatibility(yaml.safe_load(METRO.read_text(encoding="utf-8")))
    classe = next(
        campo for campo in definicao_antiga["codigo"]["segmentos"]
        if campo.get("nome") == "classe"
    )
    classe["valores"].pop("A7")
    sequencial = next(
        campo for campo in definicao_antiga["codigo"]["segmentos"]
        if campo.get("nome") == "sequencial"
    )
    sequencial["padrao_regex"] = r"\d{4}"
    perfil_modelo.definicao = definicao_antiga
    perfil_modelo.save(update_fields=["definicao"])

    codigo_a7 = "DE-15.25.00.00-6A7-1001"
    codigo_701 = "DE-15.25.00.00-6A1-701"
    previa = previa_para(
        criar_excel_pw([
            _linha(codigo_a7, "1", 1, "Em Análise", "01/02/2025", ""),
            _linha(codigo_701, "1", 1, "Em Análise", "02/02/2025", ""),
        ]),
        contrato,
        perfil_modelo,
    )
    importacao = aplicar_previa_situacao_pw(
        previa,
        contrato=contrato,
        perfil_modelo=perfil_modelo,
    )
    recusas = list(importacao.inconsistencias.order_by("numero_linha"))
    assert len(recusas) == 2
    assert all(item.categoria == "codigos_invalidos" and item.dados_linha for item in recusas)
    assert all(item.resolvida_em is None for item in recusas)

    perfil_atual = PerfilContrato.objects.create(
        contrato=contrato,
        versao=2,
        vigencia_inicio=date(2026, 11, 19),
        definicao=definicao_metro,
    )
    classe_atual = next(
        campo for campo in perfil_atual.definicao["codigo"]["segmentos"]
        if campo.get("nome") == "classe"
    )
    assert "A7" in classe_atual["valores"]

    administrador = django_user_model.objects.create_superuser(
        username="admin-reprocessa-situacao",
        email="admin-reprocessa-situacao@example.com",
        password="senha-segura",
    )
    client.force_login(administrador)
    url = reverse("linhas_recusadas", args=(contrato.pk,))

    resposta = client.post(url, {"importacao_situacao_id": importacao.pk})

    assert resposta.status_code == 200
    assert b"2 agora s\xc3\xa3o v\xc3\xa1lidas" in resposta.content
    resposta = client.post(url, {"acao": "confirmar_reprocessamento"}, follow=True)

    assert resposta.status_code == 200
    for recusa in recusas:
        recusa.refresh_from_db()
        assert recusa.resolvida_em is not None
        assert recusa.resolvida_por == administrador
    assert Documento.objects.filter(contrato=contrato).count() == 2
    assert Emissao.objects.filter(documento__contrato=contrato, revisao="1", versao=1).count() == 2
    evento = next(
        item
        for item in carregar_eventos(contrato)
        if item["acao"] == "reprocessou" and item["tipo_importacao"] == "situação do pw"
    )
    assert evento["usuario_nome"] == "admin-reprocessa-situacao"
    assert evento["validas"] == 2
    assert codigo_a7 in evento["codigo"]
    assert codigo_701 in evento["codigo"]
