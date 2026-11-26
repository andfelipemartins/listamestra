import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="BackupTentativa",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criada_em", models.DateTimeField(db_index=True, default=django.utils.timezone.now, verbose_name="iniciada em")),
                ("data_backup", models.DateField(db_index=True, verbose_name="dia do backup")),
                ("status", models.CharField(choices=[("em_andamento", "Em andamento"), ("sucesso", "Sucesso"), ("erro", "Erro")], max_length=16, verbose_name="resultado")),
                ("origem", models.CharField(choices=[("comando", "Comando"), ("preguicoso", "Disparo preguiçoso"), ("restauracao", "Cópia antes da restauração")], max_length=16, verbose_name="origem")),
                ("forcado", models.BooleanField(default=False, verbose_name="forçado")),
                ("caminho", models.CharField(blank=True, max_length=1024, verbose_name="caminho")),
                ("tamanho_bytes", models.PositiveBigIntegerField(blank=True, null=True, verbose_name="tamanho em bytes")),
                ("mensagem", models.TextField(blank=True, verbose_name="mensagem")),
            ],
            options={
                "verbose_name": "tentativa de backup",
                "verbose_name_plural": "tentativas de backup",
                "ordering": ("-criada_em", "-pk"),
            },
        ),
    ]
