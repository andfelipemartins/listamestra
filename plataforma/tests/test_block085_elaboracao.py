from datetime import date, datetime
from pathlib import Path

import pytest
import yaml
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.urls import reverse
from openpyxl import Workbook

from contratos.models import Contrato, Participacao, PerfilContrato
from documentos.models import Documento, Emissao, EmpresaElaboradora
from importacoes.elaboracao import aplicar_previa_elaboracao, gerar_previa_elaboracao
from registro.servicos import carregar_eventos
from tests.importacoes_helpers import ativar_contrato


PERFIL_METRO = Path(__file__).resolve().parents[2] / "core" / "perfil" / "exemplos" / "metro.yaml"


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato de elaboração",
        codigo_interno="CT-ELAB",
        cliente="Cliente fictício",
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
def usuario(contrato):
    modelo = get_user_model()
    pessoa = modelo.objects.create_user(
        username="gestor-elaboracao",
        first_name="Ana",
        last_name="Gestora",
        password="senha-segura",
        is_staff=True,
    )
    Participacao.objects.create(usuario=pessoa, contrato=contrato, papel=modelo.Perfil.EQUIPE)
    return pessoa


def _json_compatibility(valor):
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {chave: _json_compatibility(item) for chave, item in valor.items()}
    if isinstance(valor, list):
        return [_json_compatibility(item) for item in valor]
    return valor


def _codigo(sequencial):
    return f"DE-15.25.00.00-6A1-{sequencial:04d}"


def _documento(contrato, sequencial, empresa=None):
    return Documento.objects.create(
        contrato=contrato,
        identificador_base=_codigo(sequencial),
        titulo=f"Projeto fictício {sequencial}",
        tipo="DE",
        atributos={"tipo": "DE", "linha": "15", "trecho": "25", "classe": "A1"},
        elaborado_por=empresa,
    )


def _salvar_planilha(tmp_path, cabecalho_linha, cabecalhos, linhas, *, nome="lista.xlsx"):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Lista de documentos"
    for _ in range(cabecalho_linha - 1):
        worksheet.append(["Cabeçalho agrupador"])
    worksheet.append(cabecalhos)
    for linha in linhas:
        worksheet.append(linha)
    caminho = tmp_path / nome
    workbook.save(caminho)
    return caminho


def _gerar_previa(caminho, contrato):
    with caminho.open("rb") as arquivo:
        return gerar_previa_elaboracao(arquivo, contrato, nome_arquivo=caminho.name)


@pytest.mark.django_db
def test_empresa_normaliza_espacos_e_impede_nome_repetido_sem_diferenca_de_caixa(contrato):
    empresa = EmpresaElaboradora.objects.create(contrato=contrato, nome="  Empresa   Alfa ")

    assert empresa.nome == "Empresa Alfa"
    assert empresa.nome_normalizado == "empresa alfa"
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            EmpresaElaboradora.objects.create(contrato=contrato, nome="empresa alfa")


@pytest.mark.django_db
def test_previa_aplica_empresas_recusa_codigos_e_conflitos_e_eh_idempotente(
    tmp_path, contrato, usuario
):
    documento_um = _documento(contrato, 1)
    documento_dois = _documento(contrato, 2)
    _documento(contrato, 3)
    empresa_atual = EmpresaElaboradora.objects.create(contrato=contrato, nome="Empresa Atual")
    documento_conflito = _documento(contrato, 5, empresa=empresa_atual)

    cabecalhos = [None] * 16
    cabecalhos[9] = "CÓDIGO"
    cabecalhos[15] = "ELABORAÇÃO"
    linhas = []
    for codigo, empresa in (
        (_codigo(1), "Empresa Alfa Projetos"),
        (_codigo(1), "  EMPRESA   ALFA PROJETOS "),
        (_codigo(2), "Empresa Alfa Projetos"),
        (_codigo(3), "Empresa Beta Engenharia"),
        (_codigo(4), "Empresa Gama"),
        (_codigo(4), "Empresa Delta"),
        (_codigo(5), "Empresa Nova"),
        (_codigo(99), "Empresa Inventada"),
    ):
        linha = [None] * 16
        linha[9] = codigo
        linha[15] = empresa
        linhas.append(linha)
    caminho = _salvar_planilha(tmp_path, 2, cabecalhos, linhas)

    previa = _gerar_previa(caminho, contrato)

    assert {item["codigo"] for item in previa.documentos} == {_codigo(1), _codigo(2), _codigo(3)}
    assert previa.empresas_novas == ["Empresa Alfa Projetos", "Empresa Beta Engenharia"]
    assert previa.codigos_inexistentes == [_codigo(99)]
    assert previa.conflitos_planilha == [
        {"codigo": _codigo(4), "empresas": ["Empresa Delta", "Empresa Gama"]}
    ]
    assert previa.conflitos_existentes == [
        {
            "codigo": _codigo(5),
            "empresa_atual": "Empresa Atual",
            "empresa_planilha": "Empresa Nova",
        }
    ]

    resultado = aplicar_previa_elaboracao(previa, contrato, usuario)

    assert resultado["documentos_vinculados"] == 3
    assert resultado["empresas_criadas"] == 2
    assert resultado["conflitos"] == previa.conflitos_existentes
    documento_um.refresh_from_db()
    documento_dois.refresh_from_db()
    documento_conflito.refresh_from_db()
    assert documento_um.elaborado_por.nome == "Empresa Alfa Projetos"
    assert documento_dois.elaborado_por.nome == "Empresa Alfa Projetos"
    assert documento_conflito.elaborado_por == empresa_atual
    assert EmpresaElaboradora.objects.filter(contrato=contrato).count() == 3

    segunda_previa = _gerar_previa(caminho, contrato)
    segunda_aplicacao = aplicar_previa_elaboracao(segunda_previa, contrato, usuario)
    assert segunda_aplicacao["documentos_vinculados"] == 0
    assert segunda_aplicacao["empresas_criadas"] == 0
    assert segunda_aplicacao["ja_vinculados"] == 3
    assert EmpresaElaboradora.objects.filter(contrato=contrato).count() == 3

    eventos = carregar_eventos(contrato)
    eventos_elaboracao = [
        evento
        for evento in eventos
        if (evento.get("history_change_reason") or "").startswith("Importação da elaboração:")
    ]
    assert len(eventos_elaboracao) == 3
    assert {evento["usuario_id"] for evento in eventos_elaboracao} == {usuario.pk}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("cabecalho_linha", "cabecalhos", "indice_codigo", "indice_elaboracao"),
    [
        (1, ["elaboracao", "codigo"], 1, 0),
        (2, ["Setor", "CÓDIGO", "ElAbOrAçÃo"], 1, 2),
    ],
)
def test_localiza_colunas_pelo_nome_na_linha_um_ou_dois(
    tmp_path, contrato, cabecalho_linha, cabecalhos, indice_codigo, indice_elaboracao
):
    documento = _documento(contrato, 10)
    linha = [None] * len(cabecalhos)
    linha[indice_codigo] = _codigo(10)
    linha[indice_elaboracao] = "Projetos Fictícios Ltda"
    caminho = _salvar_planilha(tmp_path, cabecalho_linha, cabecalhos, [linha])

    previa = _gerar_previa(caminho, contrato)

    assert [item["codigo"] for item in previa.documentos] == [documento.identificador_base]
    assert previa.documentos[0]["empresa"] == "Projetos Fictícios Ltda"


@pytest.mark.django_db
def test_tela_apresenta_previa_e_so_aplica_apos_confirmacao(tmp_path, client, contrato, usuario):
    documento = _documento(contrato, 11)
    caminho = _salvar_planilha(
        tmp_path,
        1,
        ["CÓDIGO", "ELABORAÇÃO"],
        [[_codigo(11), "Projetos Alfa Fictícios"]],
    )
    client.force_login(usuario)
    ativar_contrato(client, contrato)

    resposta_previa = client.post(
        reverse("importar_elaboracao"),
        {
            "arquivo": SimpleUploadedFile(
                "lista.xlsx",
                caminho.read_bytes(),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        },
    )

    assert resposta_previa.status_code == 200
    assert "Projetos Alfa Fictícios" in resposta_previa.content.decode()
    documento.refresh_from_db()
    assert documento.elaborado_por is None

    resposta_aplicacao = client.post(reverse("importar_elaboracao"), {"acao": "confirmar"})

    assert resposta_aplicacao.status_code == 302
    documento.refresh_from_db()
    assert documento.elaborado_por.nome == "Projetos Alfa Fictícios"


@pytest.mark.django_db
def test_empresa_e_exibida_na_pasta_e_na_lista_mestra(
    client, contrato, perfil_modelo, usuario
):
    empresa = EmpresaElaboradora.objects.create(contrato=contrato, nome="Empresa Alfa Projetos")
    documento = _documento(contrato, 21, empresa=empresa)
    Emissao.objects.create(
        documento=documento,
        revisao="1",
        fase=Emissao.Fase.PRELIMINAR,
        data_emissao=date(2026, 1, 5),
        origem=Emissao.Origem.CLIENTE,
    )
    client.force_login(usuario)
    ativar_contrato(client, contrato)

    pasta = client.get(reverse("documento_pasta", args=(contrato.pk, documento.pk)))
    lista = client.get(reverse("lista_mestra"), {"contrato": contrato.pk})
    tela_importacao = client.get(reverse("importar_elaboracao"))
    hub_importacoes = client.get(reverse("importacoes_home"))

    assert pasta.status_code == 200
    assert "Elaborado por:" in pasta.content.decode()
    assert "Empresa Alfa Projetos" in pasta.content.decode()
    assert lista.status_code == 200
    assert "Elabora&#231;&#227;o" in lista.content.decode()
    assert "Empresa Alfa Projetos" in lista.content.decode()
    assert tela_importacao.status_code == 200
    assert hub_importacoes.status_code == 200
    assert reverse("importar_elaboracao") in hub_importacoes.content.decode()
