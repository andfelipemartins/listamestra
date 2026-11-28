from io import BytesIO

import pytest
from django.urls import reverse
from openpyxl import load_workbook

from contas.models import Usuario
from contratos.models import Contrato, Participacao
from documentos.models import ColunaPersonalizada, Documento
from documentos.servicos import (
    aplicar_preenchimento_lote_coluna,
    criar_coluna_personalizada,
    desativar_coluna_personalizada,
    editar_coluna_personalizada,
    salvar_valor_coluna_personalizada,
)
from registro.servicos import carregar_eventos


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato block-096b",
        codigo_interno="CT-B096B",
        cliente="Cliente de teste",
    )


@pytest.fixture
def administrador(contrato, django_user_model):
    usuario = django_user_model.objects.create_user(
        username="admin-block096b",
        password="senha-segura",
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


def _documento(contrato, sequencial):
    codigo = f"DE-15.25.00.00-6A1-{sequencial:04d}"
    return Documento.objects.create(
        contrato=contrato,
        identificador_base=codigo,
        tipo="DE",
        trecho="25",
        disciplina="A1",
        titulo=f"Documento {sequencial}",
        atributos={"tipo": "DE", "linha": "15", "trecho": "25", "sequencial": f"{sequencial:04d}"},
    )


@pytest.mark.django_db
def test_campos_personalizados_da_pasta_e_lote_aparecem_na_atividade_e_excel(
    client, contrato, administrador
):
    individual = _documento(contrato, 1001)
    em_lote = _documento(contrato, 1002)
    coluna = criar_coluna_personalizada(
        administrador,
        contrato.pk,
        nome="Retorno do cliente",
        tipo=ColunaPersonalizada.Tipo.TEXTO,
        nivel=ColunaPersonalizada.Nivel.DOCUMENTO,
    )
    salvar_valor_coluna_personalizada(
        administrador,
        contrato.pk,
        individual.pk,
        coluna.pk,
        valor="Em análise",
        motivo="Recebido na reunião",
    )
    salvar_valor_coluna_personalizada(
        administrador,
        contrato.pk,
        individual.pk,
        coluna.pk,
        valor="Aprovado",
        motivo="Confirmação por e-mail",
    )
    resultado_lote = aplicar_preenchimento_lote_coluna(
        administrador,
        contrato.pk,
        coluna.pk,
        codigos=em_lote.identificador_base,
        valor="Pendente",
        motivo="Aplicação em lote",
    )
    assert resultado_lote["aplicados"] == 1

    eventos = carregar_eventos(contrato, usuario=administrador)
    eventos_coluna = [evento for evento in eventos if evento["entidade"] == "campo personalizado"]
    assert len(eventos_coluna) == 3
    assert any("preencheu Retorno do cliente" in evento["resumo"] for evento in eventos_coluna)
    alteracao = next(evento for evento in eventos_coluna if "alterou Retorno" in evento["resumo"])
    assert "Em análise para Aprovado" in alteracao["resumo"]
    assert "Motivo: Confirmação por e-mail" in alteracao["resumo"]
    assert any(
        evento["codigo"] == em_lote.identificador_base
        and "Motivo: Aplicação em lote" in evento["resumo"]
        for evento in eventos_coluna
    )

    client.force_login(administrador)
    filtrada = client.get(
        reverse("atividade"),
        {"contrato": contrato.pk, "acao": "alterou", "codigo": "1002"},
    )
    assert filtrada.status_code == 200
    assert "Aplicação em lote" in filtrada.content.decode("utf-8")
    assert individual.identificador_base not in filtrada.content.decode("utf-8")

    resposta_excel = client.get(
        reverse("atividade"),
        {"contrato": contrato.pk, "formato": "xlsx", "acao": "alterou", "codigo": "1002"},
    )
    planilha = load_workbook(BytesIO(resposta_excel.content), read_only=True).active
    linhas = list(planilha.values)
    assert len(linhas) == 2
    assert linhas[1][4] == em_lote.identificador_base
    assert "Aplicação em lote" in linhas[1][5]


@pytest.mark.django_db
def test_criacao_edicao_e_desativacao_de_coluna_geram_eventos(contrato, administrador):
    coluna = criar_coluna_personalizada(
        administrador,
        contrato.pk,
        nome="Data de resposta",
        tipo=ColunaPersonalizada.Tipo.DATA,
        nivel=ColunaPersonalizada.Nivel.DOCUMENTO,
    )
    editar_coluna_personalizada(
        administrador,
        contrato.pk,
        coluna.pk,
        nome="Data de retorno",
    )
    desativar_coluna_personalizada(administrador, contrato.pk, coluna.pk)

    eventos = [
        evento
        for evento in carregar_eventos(contrato)
        if evento["entidade"] == "coluna personalizada"
    ]
    resumos = [evento["resumo"] for evento in eventos]
    assert any("criou a coluna Data de resposta" in resumo for resumo in resumos)
    assert any("alterou a coluna Data de retorno" in resumo for resumo in resumos)
    assert any("desativou a coluna Data de retorno" in resumo for resumo in resumos)
