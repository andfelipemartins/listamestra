from datetime import date, datetime
from io import BytesIO
from pathlib import Path

import pytest
import yaml
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from openpyxl import Workbook, load_workbook

from core.perfil import perfil_de_dict
from core.perfil.codigo import interpretar
from core.perfil.painel import classificar
from contas.models import Usuario
from contratos.models import Contrato, Participacao, PerfilContrato
from documentos.models import Analise, Documento, Emissao
from importacoes.models import ImportacaoSituacao
from importacoes.situacao_padrao import (
    aplicar_previa_situacao_padrao,
    gerar_modelo_situacao_padrao,
    gerar_previa_situacao_padrao,
)
from importacoes.views import _dados_existentes_situacao_padrao
from registro.servicos import carregar_eventos
from tests.importacoes_helpers import ativar_contrato


ROOT = Path(__file__).resolve().parents[2]
METRO = ROOT / "core" / "perfil" / "exemplos" / "metro.yaml"
SPOBRAS = ROOT / "core" / "perfil" / "exemplos" / "spobras.yaml"
CABECALHOS = [
    "Código",
    "Revisão",
    "Situação",
    "Data",
    "Observação",
    "GRD",
    "Data de envio",
    "Data de retorno",
]


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato de situação",
        codigo_interno="CT-SITUACAO",
        cliente="Cliente de teste",
    )


def criar_perfil(contrato, caminho=METRO):
    with caminho.open(encoding="utf-8") as arquivo:
        definicao = _json_compatibility(yaml.safe_load(arquivo))
    return PerfilContrato.objects.create(
        contrato=contrato,
        versao=1,
        vigencia_inicio=date(2024, 1, 1),
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


def criar_documento(contrato, perfil_modelo, codigo, revisoes, *, situacao="Em Análise", observacao=""):
    perfil = perfil_de_dict(perfil_modelo.definicao)
    interpretado = interpretar(perfil, codigo)
    documento = Documento.objects.create(
        contrato=contrato,
        identificador_base=interpretado.identificador_base,
        tipo=interpretado.segmentos.get("tipo", interpretado.segmentos.get("classificacao", "")),
    )
    emissao_resultado = []
    for revisao, data_emissao, situacao_emissao, data_analise in revisoes:
        emissao = Emissao.objects.create(
            documento=documento,
            revisao=revisao,
            versao=1 if perfil.emissao.versao else None,
            fase=Emissao.Fase.PRELIMINAR,
            data_emissao=data_emissao,
            origem=Emissao.Origem.CLIENTE,
        )
        if situacao_emissao:
            Analise.objects.create(
                emissao=emissao,
                etapa="Análise importada",
                situacao=situacao_emissao,
                data_analise=data_analise,
                observacao=observacao,
            )
        emissao_resultado.append(emissao)
    return documento, emissao_resultado


def criar_excel(linhas, cabecalhos=CABECALHOS):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(cabecalhos)
    for linha in linhas:
        worksheet.append([linha.get(cabecalho) for cabecalho in cabecalhos])
    conteudo = BytesIO()
    workbook.save(conteudo)
    workbook.close()
    conteudo.seek(0)
    return conteudo


def previa(arquivo, nome, contrato, perfil_modelo, *, data_importacao=date(2026, 11, 26)):
    return gerar_previa_situacao_padrao(
        arquivo,
        nome_arquivo=nome,
        contrato_id=contrato.pk,
        perfil_id=perfil_modelo.pk,
        perfil=perfil_de_dict(perfil_modelo.definicao),
        documentos_existentes=_dados_existentes_situacao_padrao(contrato),
        data_importacao=data_importacao,
    )


@pytest.mark.django_db
def test_modelo_tem_cabecalhos_e_aba_de_instrucoes():
    workbook = load_workbook(BytesIO(gerar_modelo_situacao_padrao()), read_only=True)
    assert workbook.sheetnames == ["Situação", "Instruções"]
    assert list(workbook["Situação"].values)[0] == tuple(CABECALHOS)
    instrucoes = " ".join(str(celula) for linha in workbook["Instruções"].values for celula in linha)
    assert "Data de retorno" in instrucoes
    assert "Data de envio são aceitas, mas ignoradas" in instrucoes
    workbook.close()


@pytest.mark.django_db
def test_previa_mostra_linhas_boas_e_ruins_sem_bloquear_validas(contrato):
    perfil_modelo = criar_perfil(contrato)
    codigo = "DE-15.25.00.00-6A1-1001"
    criar_documento(
        contrato,
        perfil_modelo,
        codigo,
        [("1", date(2025, 1, 2), "Em Análise", date(2025, 1, 3))],
    )
    arquivo = criar_excel(
        [
            {"Código": codigo, "Situação": "Não Aprovado"},
            {"Código": "CODIGO-INVALIDO", "Situação": "Aprovado"},
            {"Código": "DE-15.25.00.00-6A1-9999", "Situação": "Aprovado"},
            {"Código": codigo, "Situação": "Estado inventado"},
        ],
        ["Código", "Situação"],
    )

    resultado = previa(arquivo, "situacoes.xlsx", contrato, perfil_modelo)

    assert resultado.total_linhas == 4
    assert resultado.documentos_encontrados == 1
    assert resultado.documentos_nao_encontrados == 1
    assert resultado.codigos_invalidos == 1
    assert resultado.situacoes_invalidas == 1
    assert resultado.linhas_invalidas == 3
    assert resultado.linhas_validas == 1
    assert resultado.linhas[0].situacao == "Não Aprovado"


@pytest.mark.django_db
def test_revisao_e_data_vazias_usam_ultima_revisao_e_data_da_importacao(contrato):
    perfil_modelo = criar_perfil(contrato)
    codigo = "DE-15.25.00.00-6A1-1002"
    _, emissoes = criar_documento(
        contrato,
        perfil_modelo,
        codigo,
        [
            ("1", date(2025, 1, 2), "Em Análise", date(2025, 1, 3)),
            ("2", date(2025, 3, 2), "Não Aprovado", date(2025, 3, 3)),
        ],
    )

    resultado = previa(
        criar_excel([{"Código": codigo, "Situação": "Aprovado"}], ["Código", "Situação"]),
        "situacoes.xlsx",
        contrato,
        perfil_modelo,
    )

    linha = resultado.linhas[0]
    assert linha.revisao == "2"
    assert linha.emissao_id == emissoes[-1].pk
    assert linha.data_analise == date(2026, 11, 26)


@pytest.mark.django_db
def test_coluna_opcional_ausente_preserva_observacao(contrato):
    perfil_modelo = criar_perfil(contrato)
    codigo = "DE-15.25.00.00-6A1-1003"
    _, emissoes = criar_documento(
        contrato,
        perfil_modelo,
        codigo,
        [("1", date(2025, 1, 2), "Aprovado", date(2026, 11, 26))],
        observacao="Observação que deve permanecer",
    )
    lote = previa(
        criar_excel([{"Código": codigo, "Situação": "Aprovado"}], ["Código", "Situação"]),
        "situacoes.xlsx",
        contrato,
        perfil_modelo,
    )

    aplicar_previa_situacao_padrao(
        lote,
        contrato=contrato,
        perfil_modelo=perfil_modelo,
    )

    analise = Analise.objects.get(emissao=emissoes[0])
    assert analise.observacao == "Observação que deve permanecer"


@pytest.mark.django_db
def test_campos_sem_destino_sao_mostrados_como_ignorados(contrato):
    perfil_modelo = criar_perfil(contrato)
    codigo = "DE-15.25.00.00-6A1-1008"
    criar_documento(
        contrato,
        perfil_modelo,
        codigo,
        [("1", date(2025, 1, 2), "Em Análise", date(2025, 1, 3))],
    )

    resultado = previa(
        criar_excel(
            [
                {
                    "Código": codigo,
                    "GRD": "GRD-123",
                    "Data de envio": date(2026, 11, 20),
                    "Data de retorno": date(2026, 11, 25),
                }
            ]
        ),
        "situacoes.xlsx",
        contrato,
        perfil_modelo,
    )

    assert resultado.linhas_validas == 1
    assert {campo.nome for campo in resultado.linhas[0].campos_ignorados} == {
        "GRD",
        "Data de envio",
    }
    assert resultado.linhas[0].data_analise == date(2026, 11, 25)


@pytest.mark.django_db
def test_cancelado_da_planilha_e_classificado_pelo_perfil(contrato):
    perfil_modelo = criar_perfil(contrato)
    codigo = "DE-15.25.00.00-6A1-1004"
    documento, emissoes = criar_documento(
        contrato,
        perfil_modelo,
        codigo,
        [("1", date(2025, 1, 2), "Em Análise", date(2025, 1, 3))],
    )
    lote = previa(
        criar_excel([{"Código": codigo, "Situação": "Cancelado"}], ["Código", "Situação"]),
        "cancelamento.xlsx",
        contrato,
        perfil_modelo,
    )

    aplicar_previa_situacao_padrao(lote, contrato=contrato, perfil_modelo=perfil_modelo)

    cancelamento = Analise.objects.filter(emissao=emissoes[0]).latest("pk")
    assert cancelamento.situacao == "Cancelado"
    assert classificar(perfil_de_dict(perfil_modelo.definicao), cancelamento.situacao).id == "cancelado"
    assert documento.ativo


@pytest.mark.django_db
def test_aplicacao_registra_arquivo_usuario_e_observacao_na_atividade(contrato):
    perfil_modelo = criar_perfil(contrato)
    usuario = get_user_model().objects.create_user(username="editor", password="senha")
    Participacao.objects.create(usuario=usuario, contrato=contrato, papel=Usuario.Perfil.EQUIPE)
    codigo = "DE-15.25.00.00-6A1-1005"
    _, emissoes = criar_documento(
        contrato,
        perfil_modelo,
        codigo,
        [("1", date(2025, 1, 2), "Em Análise", date(2025, 1, 3))],
    )
    lote = previa(
        criar_excel(
            [{"Código": codigo, "Situação": "Não Aprovado", "Observação": "Retornar ao projetista"}],
            ["Código", "Situação", "Observação"],
        ),
        "lote-externo.xlsx",
        contrato,
        perfil_modelo,
    )

    importacao = aplicar_previa_situacao_padrao(
        lote,
        contrato=contrato,
        perfil_modelo=perfil_modelo,
        usuario=usuario,
    )

    assert Analise.objects.filter(emissao=emissoes[0], situacao="Não Aprovado", observacao="Retornar ao projetista").exists()
    assert importacao.importado_por == usuario
    assert importacao.arquivo_nome.endswith("lote-externo.xlsx")
    evento = next(
        item
        for item in carregar_eventos(contrato)
        if item.get("importacao_id") == importacao.pk
    )
    assert evento["usuario"] == usuario
    assert "lote-externo.xlsx" in evento["resumo"]


@pytest.mark.django_db
def test_permissoes_deixam_admin_e_editor_importarem_e_bloqueiam_leitor(contrato):
    perfil_modelo = criar_perfil(contrato)
    codigo = "DE-15.25.00.00-6A1-1006"
    criar_documento(
        contrato,
        perfil_modelo,
        codigo,
        [("1", date(2025, 1, 2), "Em Análise", date(2025, 1, 3))],
    )
    url = reverse("importar_situacao_padrao")
    for indice, papel in enumerate((Usuario.Perfil.ADMIN, Usuario.Perfil.EQUIPE)):
        usuario = get_user_model().objects.create_user(username=f"operador{indice}", password="senha")
        Participacao.objects.create(usuario=usuario, contrato=contrato, papel=papel)
        client = Client()
        client.force_login(usuario)
        ativar_contrato(client, contrato)
        resposta = client.post(
            url,
            {
                "acao": "prever",
                "arquivo": SimpleUploadedFile(
                    f"lote{indice}.xlsx",
                    criar_excel([{"Código": codigo, "Situação": "Aprovado"}], ["Código", "Situação"]).getvalue(),
                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
        )
        assert resposta.status_code == 200
        assert b"Aplicar linhas v\xc3\xa1lidas" in resposta.content
        resposta_aplicar = client.post(url, {"acao": "aplicar"})
        assert resposta_aplicar.status_code == 302

    leitor = get_user_model().objects.create_user(username="leitor", password="senha")
    Participacao.objects.create(usuario=leitor, contrato=contrato, papel=Usuario.Perfil.CHEFIA)
    cliente_leitor = Client()
    cliente_leitor.force_login(leitor)
    ativar_contrato(cliente_leitor, contrato)
    assert cliente_leitor.get(url).status_code == 403
    assert cliente_leitor.post(url, {"acao": "prever"}).status_code == 403
    assert cliente_leitor.get(reverse("modelo_situacao_padrao")).status_code == 403


@pytest.mark.django_db
def test_perfil_spobras_aceita_sinonimo_configurado(contrato):
    perfil_modelo = criar_perfil(contrato, SPOBRAS)
    codigo = "DE-CC-EE-WW-5E-001-A"
    criar_documento(
        contrato,
        perfil_modelo,
        codigo,
        [("A", date(2025, 1, 2), "ENTREGUE", date(2025, 1, 3))],
    )

    resultado = previa(
        criar_excel([{"Código": codigo, "Situação": "DEVOLVIDO"}], ["Código", "Situação"]),
        "spobras.xlsx",
        contrato,
        perfil_modelo,
    )

    assert resultado.linhas_validas == 1
    assert resultado.linhas[0].situacao == "DEVOLVIDO"


@pytest.mark.django_db
def test_csv_aceita_cabecalhos_sem_acento_em_maiusculas(contrato):
    perfil_modelo = criar_perfil(contrato)
    codigo = "DE-15.25.00.00-6A1-1007"
    criar_documento(
        contrato,
        perfil_modelo,
        codigo,
        [("1", date(2025, 1, 2), "Em Análise", date(2025, 1, 3))],
    )
    arquivo = BytesIO(f"CODIGO;SITUACAO;OBSERVACAO\n{codigo};APROVADO;\n".encode("utf-8"))

    resultado = previa(arquivo, "situacoes.csv", contrato, perfil_modelo)

    assert resultado.linhas_validas == 1
    assert resultado.linhas[0].situacao == "Aprovado"
