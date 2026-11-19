from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("importacoes", "0007_indicedocumentos_fase_conta_no_previsto"),
    ]

    operations = [
        migrations.AddField(
            model_name="indicedocumentos",
            name="escopo",
            field=models.CharField(blank=True, max_length=100, verbose_name="escopo"),
        ),
        migrations.AddField(
            model_name="historicalindicedocumentos",
            name="escopo",
            field=models.CharField(blank=True, max_length=100, verbose_name="escopo"),
        ),
    ]
