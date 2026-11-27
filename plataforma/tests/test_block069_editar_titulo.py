from datetime import date, datetime
from io import BytesIO
from pathlib import Path

import pytest
import yaml
from django.urls import reverse
from openpyxl import Workbook

from contas.models import Usuario
from contratos.models import Contrato, Participacao, PerfilContrato
from core.perfil import perfil_de_dict
from documentos.models import Documento
from documentos.servicos import editar_titulo_documento
from importacoes.id_excel import FORMATOS_ID, gerar_previa_id
from importacoes.services import aplicar_previa
from registro.servicos import carregar_eventos


PERFIL_METRO = Path(__file__).resolve().parents[2] / "core" / "perfil" / "exemplos" / "metro.yaml"
CODIGO = "DE-15.25.00.00-6A1-1001"


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato do block-069",
        codigo_interno="CT-B069",
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
        username="admin-block069",
        password="senha",
        first_name="Ana",
        last_name="Administradora",
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
        titulo="Título atual",
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
def test_admin_edita_titulo_com_motivo_e_historico(
    client, contrato, perfil_modelo, documento, admin_contrato
):
    client.force_login(admin_contrato)
    pasta_url = reverse("documento_pasta", args=(contrato.pk, documento.pk))
    edicao_url = reverse("documento_editar_titulo", args=(contrato.pk, documento.pk))

    pasta = client.get(pasta_url)
    assert pasta.status_code == 200
    assert "Editar título" in pasta.content.decode()
    formulario = client.get(edicao_url)
    assert formulario.status_code == 200
    assert 'value="Título atual"' in formulario.content.decode()

    resposta = client.post(
        edicao_url,
        {"titulo": "Título revisado", "motivo": "Corrigir título conforme cadastro aprovado"},
        follow=True,
    )

    assert resposta.status_code == 200
    assert "Título atualizado." in resposta.content.decode()
    documento.refresh_from_db()
    assert documento.titulo == "Título revisado"
    historico = documento.history.latest()
    assert historico.history_change_reason == "Corrigir título conforme cadastro aprovado"
    assert historico.history_user == admin_contrato


@pytest.mark.django_db
@pytest.mark.parametrize("papel", [Usuario.Perfil.EQUIPE, Usuario.Perfil.CHEFIA])
def test_equipe_sem_permissao_nao_ve_acao_e_recebe_403_no_post(
    papel, client, contrato, perfil_modelo, documento, django_user_model
):
    usuario = django_user_model.objects.create_user(username=f"sem-edicao-{papel}", password="senha")
    Participacao.objects.create(
        usuario=usuario,
        contrato=contrato,
        papel=papel,
        ativo=True,
    )
    client.force_login(usuario)
    pasta_url = reverse("documento_pasta", args=(contrato.pk, documento.pk))
    edicao_url = reverse("documento_editar_titulo", args=(contrato.pk, documento.pk))

    pasta = client.get(pasta_url)
    assert pasta.status_code == 200
    assert "Editar título" not in pasta.content.decode()

    client.raise_request_exception = False
    resposta = client.post(
        edicao_url,
        {"titulo": "Título indevido", "motivo": "Tentativa não autorizada"},
    )
    assert resposta.status_code == 403
    documento.refresh_from_db()
    assert documento.titulo == "Título atual"


@pytest.mark.django_db
@pytest.mark.parametrize("titulo", ["", "   ", "Título atual"])
def test_titulo_vazio_ou_igual_e_recusado(
    titulo, client, contrato, perfil_modelo, documento, admin_contrato
):
    client.force_login(admin_contrato)
    url = reverse("documento_editar_titulo", args=(contrato.pk, documento.pk))

    resposta = client.post(url, {"titulo": titulo, "motivo": "Motivo válido"})

    assert resposta.status_code == 400
    documento.refresh_from_db()
    assert documento.titulo == "Título atual"
    assert documento.history.count() == 1


@pytest.mark.django_db
def test_motivo_obrigatorio(client, contrato, perfil_modelo, documento, admin_contrato):
    client.force_login(admin_contrato)
    url = reverse("documento_editar_titulo", args=(contrato.pk, documento.pk))

    resposta = client.post(url, {"titulo": "Título revisado", "motivo": "   "})

    assert resposta.status_code == 400
    documento.refresh_from_db()
    assert documento.titulo == "Título atual"
    assert documento.history.count() == 1


@pytest.mark.django_db
def test_alteracao_aparece_na_atividade_com_diferenca_autor_e_motivo(
    client, contrato, perfil_modelo, documento, admin_contrato
):
    client.force_login(admin_contrato)
    motivo = "Ajustar conforme revisão do cadastro"
    editar_titulo_documento(
        admin_contrato,
        contrato.pk,
        documento.pk,
        "Título revisado",
        motivo,
    )

    evento = next(
        item
        for item in carregar_eventos(contrato)
        if item["acao_rotulo"] == "Título alterado"
    )
    assert evento["usuario_nome"] == "Ana Administradora"
    assert "Título atual → Título revisado" in evento["resumo"]
    assert evento["detalhes"] == [
        {"campo": "Título", "antes": "Título atual", "depois": "Título revisado"},
        {"campo": "Motivo", "antes": "", "depois": motivo},
    ]

    resposta = client.get(
        reverse("atividade"),
        {"contrato": contrato.pk, "evento": evento["chave"]},
    )
    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Título alterado" in html
    assert "Ana Administradora" in html
    assert "Título atual" in html
    assert "Título revisado" in html
    assert motivo in html


@pytest.mark.django_db
def test_reimportacao_id_mantem_titulo_editado_e_marca_divergencia(
    contrato, perfil_modelo, documento, admin_contrato
):
    editar_titulo_documento(
        admin_contrato,
        contrato.pk,
        documento.pk,
        "Título editado manualmente",
        "Atualização solicitada pela coordenação",
    )
    documento.refresh_from_db()
    formato = FORMATOS_ID["excel_id"]
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = formato["planilha"]
    worksheet.append(
        [
            formato["cabecalho_titulo"],
            *formato["cabecalhos_segmentos"].values(),
            formato["cabecalho_codigo"],
            formato["cabecalho_excluido"],
        ]
    )
    worksheet.append(
        ["Título do ID", "DE", "15", "25", "00", "00", "6", "A1", "1001", CODIGO, 0]
    )
    arquivo = BytesIO()
    workbook.save(arquivo)
    arquivo.seek(0)
    previa = gerar_previa_id(
        arquivo,
        nome_arquivo="ID-block069.xlsx",
        contrato_id=contrato.pk,
        perfil_id=perfil_modelo.pk,
        perfil=perfil_de_dict(perfil_modelo.definicao),
        documentos_existentes=[(documento.identificador_base, documento.titulo)],
        codigo_indice="ID-BLOCK069",
        revisao="1",
    )

    assert previa.linhas[0].categoria == "titulos_divergentes"
    aplicar_previa(
        previa,
        contrato=contrato,
        perfil_modelo=perfil_modelo,
        usuario=admin_contrato,
    )

    documento.refresh_from_db()
    assert documento.titulo == "Título editado manualmente"
