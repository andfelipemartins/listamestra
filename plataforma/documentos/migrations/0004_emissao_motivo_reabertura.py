from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documentos", "0003_analise_origem_documento_fora_do_id_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="emissao",
            name="motivo_reabertura",
            field=models.CharField(
                blank=True,
                choices=[
                    ("campo", "Problema de campo"),
                    ("projeto", "Erro de projeto"),
                    ("cliente", "Pedido do cliente"),
                    ("outro", "Outro"),
                ],
                default="",
                max_length=20,
                verbose_name="motivo da reabertura",
            ),
        ),
        migrations.AddField(
            model_name="emissao",
            name="motivo_reabertura_obs",
            field=models.CharField(
                blank=True,
                default="",
                max_length=300,
                verbose_name="observação do motivo da reabertura",
            ),
        ),
        migrations.AddField(
            model_name="historicalemissao",
            name="motivo_reabertura",
            field=models.CharField(
                blank=True,
                choices=[
                    ("campo", "Problema de campo"),
                    ("projeto", "Erro de projeto"),
                    ("cliente", "Pedido do cliente"),
                    ("outro", "Outro"),
                ],
                default="",
                max_length=20,
                verbose_name="motivo da reabertura",
            ),
        ),
        migrations.AddField(
            model_name="historicalemissao",
            name="motivo_reabertura_obs",
            field=models.CharField(
                blank=True,
                default="",
                max_length=300,
                verbose_name="observação do motivo da reabertura",
            ),
        ),
    ]
