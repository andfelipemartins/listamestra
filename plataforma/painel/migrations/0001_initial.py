import django.db.models.deletion
import simple_history.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("contratos", "0004_escopocontrato"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FotoPainel",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("data", models.DateField(verbose_name="data da foto")),
                ("numeros", models.JSONField(default=dict, verbose_name="números")),
                ("criado_em", models.DateTimeField(auto_now=True, verbose_name="guardado em")),
                (
                    "contrato",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fotos_painel",
                        to="contratos.contrato",
                        verbose_name="contrato",
                    ),
                ),
                (
                    "criado_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="fotos_painel_guardadas",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="guardado por",
                    ),
                ),
            ],
            options={
                "verbose_name": "foto do Painel",
                "verbose_name_plural": "fotos do Painel",
                "ordering": ("-data",),
            },
        ),
        migrations.CreateModel(
            name="HistoricalFotoPainel",
            fields=[
                (
                    "id",
                    models.BigIntegerField(
                        auto_created=True,
                        blank=True,
                        db_index=True,
                        verbose_name="ID",
                    ),
                ),
                ("data", models.DateField(verbose_name="data da foto")),
                ("numeros", models.JSONField(default=dict, verbose_name="números")),
                ("criado_em", models.DateTimeField(blank=True, editable=False, verbose_name="guardado em")),
                ("history_id", models.AutoField(primary_key=True, serialize=False)),
                ("history_date", models.DateTimeField(db_index=True)),
                ("history_change_reason", models.CharField(max_length=100, null=True)),
                (
                    "history_type",
                    models.CharField(choices=[("+", "Created"), ("~", "Changed"), ("-", "Deleted")], max_length=1),
                ),
                (
                    "contrato",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="contratos.contrato",
                        verbose_name="contrato",
                    ),
                ),
                (
                    "criado_por",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="guardado por",
                    ),
                ),
                (
                    "history_user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "historical foto do Painel",
                "verbose_name_plural": "historical fotos do Painel",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": ("history_date", "history_id"),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.AddConstraint(
            model_name="fotopainel",
            constraint=models.UniqueConstraint(
                fields=("contrato", "data"),
                name="foto_painel_contrato_data_unica",
            ),
        ),
    ]
