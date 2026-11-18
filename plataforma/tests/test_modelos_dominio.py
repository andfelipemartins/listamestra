from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse

from contratos.models import Contrato, Participacao, PerfilContrato
from documentos.models import CodigoDocumento, Documento, Emissao


@pytest.fixture
def contrato():
    return Contrato.objects.create(
        nome="Contrato de teste",
        codigo_interno="CT-001",
        cliente="Cliente de teste",
    )


@pytest.fixture
def perfil(contrato):
    return PerfilContrato.objects.create(
        contrato=contrato,
        versao=1,
        vigencia_inicio=date(2026, 1, 1),
        definicao={"codigo": {"segmentos": []}},
    )


@pytest.mark.django_db
def test_perfil_vigente_escolhe_ultima_vigencia_e_ignora_inativos(contrato):
    antigo = PerfilContrato.objects.create(
        contrato=contrato,
        versao=1,
        vigencia_inicio=date(2026, 1, 1),
    )
    PerfilContrato.objects.create(
        contrato=contrato,
        versao=2,
        vigencia_inicio=date(2026, 5, 1),
        ativo=False,
    )
    vigente = PerfilContrato.objects.create(
        contrato=contrato,
        versao=3,
        vigencia_inicio=date(2026, 4, 1),
    )

    assert PerfilContrato.perfil_vigente(contrato, date(2026, 3, 31)) == antigo
    assert PerfilContrato.perfil_vigente(contrato, date(2026, 6, 1)) == vigente
    assert PerfilContrato.perfil_vigente(contrato, date(2025, 12, 31)) is None


@pytest.mark.django_db
def test_documento_pode_ter_um_codigo_por_perfil(contrato, perfil):
    outro_perfil = PerfilContrato.objects.create(
        contrato=contrato,
        versao=2,
        vigencia_inicio=date(2026, 7, 1),
    )
    documento = Documento.objects.create(contrato=contrato, identificador_base="DOC-001")
    CodigoDocumento.objects.create(
        documento=documento,
        perfil=perfil,
        codigo="PADRAO-A-001",
    )
    CodigoDocumento.objects.create(
        documento=documento,
        perfil=outro_perfil,
        codigo="PADRAO-B-009",
    )
    assert documento.codigos.count() == 2


@pytest.mark.django_db
def test_constraint_rejeita_segundo_codigo_do_mesmo_perfil_no_documento(contrato, perfil):
    documento = Documento.objects.create(contrato=contrato, identificador_base="DOC-002")
    CodigoDocumento.objects.create(
        documento=documento,
        perfil=perfil,
        codigo="COD-1",
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        CodigoDocumento.objects.create(
            documento=documento,
            perfil=perfil,
            codigo="COD-2",
        )


@pytest.mark.django_db
def test_unicidade_de_documento_por_contrato(contrato):
    Documento.objects.create(contrato=contrato, identificador_base="DOC-003")

    with pytest.raises(IntegrityError), transaction.atomic():
        Documento.objects.create(contrato=contrato, identificador_base="DOC-003")


@pytest.mark.django_db
def test_unicidade_de_emissao_por_revisao_e_versao(contrato):
    documento = Documento.objects.create(contrato=contrato, identificador_base="DOC-004")
    dados = {
        "documento": documento,
        "revisao": "A",
        "versao": 1,
        "fase": Emissao.Fase.PRELIMINAR,
        "data_emissao": date(2026, 8, 1),
        "origem": Emissao.Origem.PROJETISTA,
    }
    Emissao.objects.create(**dados)
    Emissao.objects.create(**{**dados, "versao": 2})

    with pytest.raises(IntegrityError), transaction.atomic():
        Emissao.objects.create(**dados)


@pytest.mark.django_db
def test_unicidade_de_emissao_sem_versao(contrato):
    documento = Documento.objects.create(contrato=contrato, identificador_base="DOC-005")
    dados = {
        "documento": documento,
        "revisao": "0",
        "versao": None,
        "fase": Emissao.Fase.ORIGINAL,
        "data_emissao": date(2026, 9, 1),
        "origem": Emissao.Origem.CLIENTE,
    }
    Emissao.objects.create(**dados)

    with pytest.raises(IntegrityError), transaction.atomic():
        Emissao.objects.create(**dados)


@pytest.mark.django_db
def test_alteracao_de_titulo_gera_historico(contrato):
    documento = Documento.objects.create(
        contrato=contrato,
        identificador_base="DOC-006",
        titulo="Título original",
    )
    documento.titulo = "Título atualizado"
    documento.save()

    historicos = list(documento.history.order_by("history_date"))
    assert len(historicos) == 2
    assert historicos[0].titulo == "Título original"
    assert historicos[1].titulo == "Título atualizado"


@pytest.mark.django_db
def test_usuario_pode_ter_papeis_diferentes_em_contratos(django_user_model):
    usuario = django_user_model.objects.create_user(username="ana", password="senha-segura")
    primeiro = Contrato.objects.create(nome="Contrato A", codigo_interno="A", cliente="Cliente")
    segundo = Contrato.objects.create(nome="Contrato B", codigo_interno="B", cliente="Cliente")

    Participacao.objects.create(usuario=usuario, contrato=primeiro, papel="admin")
    Participacao.objects.create(usuario=usuario, contrato=segundo, papel="projetista")

    assert list(
        Participacao.objects.filter(usuario=usuario).order_by("contrato__codigo_interno").values_list("papel", flat=True)
    ) == ["admin", "projetista"]


@pytest.mark.django_db
def test_listagens_admin_dos_modelos_de_dominio(client, django_user_model):
    administrador = django_user_model.objects.create_superuser(
        username="admin", email="admin@example.com", password="senha-segura"
    )
    client.force_login(administrador)

    modelos = (
        "contratos_contrato",
        "contratos_perfilcontrato",
        "contratos_participacao",
        "documentos_documento",
        "documentos_codigodocumento",
        "documentos_emissao",
        "documentos_analise",
    )
    for modelo in modelos:
        response = client.get(reverse(f"admin:{modelo}_changelist"))
        assert response.status_code == 200, modelo
