from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documentos", "0006_motivo_cancelamento_por_perfil"),
    ]

    operations = [
        migrations.AddField(
            model_name="documento",
            name="observacao_reativacao",
            field=models.CharField(
                blank=True,
                default="",
                max_length=1000,
                verbose_name="observação da reativação",
            ),
        ),
        migrations.AddField(
            model_name="historicaldocumento",
            name="observacao_reativacao",
            field=models.CharField(
                blank=True,
                default="",
                max_length=1000,
                verbose_name="observação da reativação",
            ),
        ),
    ]
