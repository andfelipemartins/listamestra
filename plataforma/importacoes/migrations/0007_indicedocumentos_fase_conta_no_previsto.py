from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("importacoes", "0006_historicalinconsistenciaimportacao_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="indicedocumentos",
            name="fase",
            field=models.CharField(blank=True, max_length=100, verbose_name="fase"),
        ),
        migrations.AddField(
            model_name="indicedocumentos",
            name="conta_no_previsto",
            field=models.BooleanField(default=True, verbose_name="conta no previsto"),
        ),
        migrations.AddField(
            model_name="historicalindicedocumentos",
            name="fase",
            field=models.CharField(blank=True, max_length=100, verbose_name="fase"),
        ),
        migrations.AddField(
            model_name="historicalindicedocumentos",
            name="conta_no_previsto",
            field=models.BooleanField(default=True, verbose_name="conta no previsto"),
        ),
    ]
