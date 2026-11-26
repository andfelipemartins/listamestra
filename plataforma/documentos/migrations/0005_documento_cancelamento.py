import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


MOTIVOS_CANCELAMENTO = [
    ("desmembrado", "Desmembrado em outros documentos"),
    ("incorporado", "Incorporado a outro documento"),
    ("substituido", "Substituído por outro documento"),
    ("cliente", "Pedido do cliente"),
    ("fora_escopo", "Fora do escopo"),
    ("inviavel", "Inviável (constatado em campo)"),
    ("solucao", "Mudança de solução de projeto"),
    ("duplicado", "Duplicado / código em dobro"),
    ("outro", "Outro"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("documentos", "0004_emissao_motivo_reabertura"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="documento",
            name="cancelado_em",
            field=models.DateTimeField(blank=True, null=True, verbose_name="cancelado em"),
        ),
        migrations.AddField(
            model_name="documento",
            name="cancelado_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="documentos_cancelados",
                to=settings.AUTH_USER_MODEL,
                verbose_name="cancelado por",
            ),
        ),
        migrations.AddField(
            model_name="documento",
            name="motivo_cancelamento",
            field=models.CharField(
                blank=True,
                choices=MOTIVOS_CANCELAMENTO,
                default="",
                max_length=20,
                verbose_name="motivo do cancelamento",
            ),
        ),
        migrations.AddField(
            model_name="documento",
            name="motivo_cancelamento_obs",
            field=models.CharField(
                blank=True,
                default="",
                max_length=1000,
                verbose_name="observação do cancelamento",
            ),
        ),
        migrations.AddField(
            model_name="historicaldocumento",
            name="cancelado_em",
            field=models.DateTimeField(blank=True, null=True, verbose_name="cancelado em"),
        ),
        migrations.AddField(
            model_name="historicaldocumento",
            name="cancelado_por",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
                verbose_name="cancelado por",
            ),
        ),
        migrations.AddField(
            model_name="historicaldocumento",
            name="motivo_cancelamento",
            field=models.CharField(
                blank=True,
                choices=MOTIVOS_CANCELAMENTO,
                default="",
                max_length=20,
                verbose_name="motivo do cancelamento",
            ),
        ),
        migrations.AddField(
            model_name="historicaldocumento",
            name="motivo_cancelamento_obs",
            field=models.CharField(
                blank=True,
                default="",
                max_length=1000,
                verbose_name="observação do cancelamento",
            ),
        ),
    ]
