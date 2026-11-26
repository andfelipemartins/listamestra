from datetime import datetime, timezone as datetime_timezone

import pytest
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from contratos.admin import ContratoAdmin, EscopoContratoInline
from contratos.models import Contrato, EscopoContrato
from importacoes.admin import IndiceDocumentosAdminForm
from importacoes.models import IndiceDocumentos


@pytest.fixture
def contrato(db):
    return Contrato.objects.create(
        nome="Contrato de escopos",
        codigo_interno="CT-ESCOPO",
        cliente="Cliente de teste",
    )


@pytest.mark.django_db
def test_escopos_sao_unicos_sem_diferenciar_maiusculas_e_ordenados(contrato):
    EscopoContrato.objects.create(contrato=contrato, nome="Civil")
    duplicado = EscopoContrato(contrato=contrato, nome="cIVIL")

    with pytest.raises(ValidationError, match="já existe"):
        duplicado.full_clean()
    with pytest.raises(IntegrityError), transaction.atomic():
        EscopoContrato.objects.create(contrato=contrato, nome="CIVIL")

    outro = Contrato.objects.create(
        nome="Outro contrato de escopos",
        codigo_interno="CT-ESCOPO-2",
        cliente="Outro cliente",
    )
    EscopoContrato.objects.create(contrato=outro, nome="Civil")
    EscopoContrato.objects.create(contrato=contrato, nome="Arquitetura")

    assert list(EscopoContrato.objects.filter(contrato=contrato).values_list("nome", flat=True)) == [
        "Arquitetura",
        "Civil",
    ]


@pytest.mark.django_db
def test_id_recusa_escopo_de_outro_contrato(contrato):
    outro = Contrato.objects.create(
        nome="Contrato sem vínculo",
        codigo_interno="CT-SEM-VINCULO",
        cliente="Outro cliente",
    )
    escopo = EscopoContrato.objects.create(contrato=outro, nome="Sistemas")
    indice = IndiceDocumentos.objects.create(
        contrato=contrato,
        codigo="ID-TESTE",
        revisao="1",
        fonte=IndiceDocumentos.Fonte.EXCEL_ID,
        arquivo_nome="ID.xlsx",
        importado_em=timezone.now(),
    )

    with pytest.raises(ValidationError, match="mesmo contrato"), transaction.atomic():
        indice.escopos.add(escopo)

    assert not indice.escopos.exists()


@pytest.mark.django_db
def test_admin_cadastra_escopos_no_contrato_e_exibe_caixinhas_no_id(contrato):
    admin = ContratoAdmin(Contrato, AdminSite())
    formulario_id = IndiceDocumentosAdminForm()

    assert EscopoContratoInline in admin.inlines
    assert formulario_id.fields["escopos"].widget.__class__.__name__ == "CheckboxSelectMultiple"
    assert list(formulario_id.fields["escopos"].queryset) == []


@pytest.mark.django_db(transaction=True)
def test_migracao_converte_textos_em_escopos_do_contrato():
    executor = MigrationExecutor(connection)
    folhas = executor.loader.graph.leaf_nodes()
    alvo_antigo = [("importacoes", "0008_indicedocumentos_escopo")]
    executor.migrate(alvo_antigo)

    try:
        apps_antigos = MigrationExecutor(connection).loader.project_state(alvo_antigo).apps
        ContratoAntigo = apps_antigos.get_model("contratos", "Contrato")
        IndiceAntigo = apps_antigos.get_model("importacoes", "IndiceDocumentos")
        contrato_a = ContratoAntigo.objects.create(
            nome="Contrato migração A",
            codigo_interno="CT-MIG-A",
            cliente="Cliente A",
        )
        contrato_b = ContratoAntigo.objects.create(
            nome="Contrato migração B",
            codigo_interno="CT-MIG-B",
            cliente="Cliente B",
        )
        agora = datetime.now(datetime_timezone.utc)
        ids = [
            IndiceAntigo.objects.create(
                contrato=contrato_a,
                codigo="ID-A-1",
                revisao="1",
                fase="Fase 1",
                escopo=" Civil ",
                fonte="excel_id",
                arquivo_nome="ID-A-1.xlsx",
                importado_em=agora,
            ),
            IndiceAntigo.objects.create(
                contrato=contrato_a,
                codigo="ID-A-2",
                revisao="1",
                fase="Fase 1",
                escopo="civil",
                fonte="excel_id",
                arquivo_nome="ID-A-2.xlsx",
                importado_em=agora,
            ),
            IndiceAntigo.objects.create(
                contrato=contrato_a,
                codigo="ID-A-3",
                revisao="1",
                fonte="excel_id",
                arquivo_nome="ID-A-3.xlsx",
                importado_em=agora,
            ),
            IndiceAntigo.objects.create(
                contrato=contrato_b,
                codigo="ID-B-1",
                revisao="1",
                fase="Fase 2",
                escopo="Civil",
                fonte="excel_id",
                arquivo_nome="ID-B-1.xlsx",
                importado_em=agora,
            ),
        ]

        alvo_novo = [("importacoes", "0009_remove_historicalindicedocumentos_escopo_and_more")]
        MigrationExecutor(connection).migrate(alvo_novo)
        apps_novos = MigrationExecutor(connection).loader.project_state(alvo_novo).apps
        IndiceNovo = apps_novos.get_model("importacoes", "IndiceDocumentos")
        EscopoNovo = apps_novos.get_model("contratos", "EscopoContrato")

        civil_a = EscopoNovo.objects.get(contrato_id=contrato_a.pk, nome="Civil")
        civil_b = EscopoNovo.objects.get(contrato_id=contrato_b.pk, nome="Civil")
        assert civil_a.pk != civil_b.pk
        assert EscopoNovo.objects.filter(contrato_id=contrato_a.pk).count() == 1
        assert set(
            IndiceNovo.objects.get(pk=ids[0].pk).escopos.values_list("pk", flat=True)
        ) == {civil_a.pk}
        assert set(
            IndiceNovo.objects.get(pk=ids[1].pk).escopos.values_list("pk", flat=True)
        ) == {civil_a.pk}
        assert not IndiceNovo.objects.get(pk=ids[2].pk).escopos.exists()
        assert set(
            IndiceNovo.objects.get(pk=ids[3].pk).escopos.values_list("pk", flat=True)
        ) == {civil_b.pk}
    finally:
        MigrationExecutor(connection).migrate(folhas)
