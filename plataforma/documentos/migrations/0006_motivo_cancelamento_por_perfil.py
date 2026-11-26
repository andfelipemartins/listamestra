from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documentos", "0005_documento_cancelamento"),
    ]

    operations = [
        migrations.AlterField(
            model_name="documento",
            name="motivo_cancelamento",
            field=models.CharField(
                blank=True,
                default="",
                max_length=50,
                verbose_name="motivo do cancelamento",
            ),
        ),
        migrations.AlterField(
            model_name="historicaldocumento",
            name="motivo_cancelamento",
            field=models.CharField(
                blank=True,
                default="",
                max_length=50,
                verbose_name="motivo do cancelamento",
            ),
        ),
    ]
