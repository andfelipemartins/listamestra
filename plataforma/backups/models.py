from django.db import models
from django.utils import timezone


class BackupTentativa(models.Model):
    class Status(models.TextChoices):
        EM_ANDAMENTO = "em_andamento", "Em andamento"
        SUCESSO = "sucesso", "Sucesso"
        ERRO = "erro", "Erro"

    class Origem(models.TextChoices):
        COMANDO = "comando", "Comando"
        PREGUICOSO = "preguicoso", "Disparo preguiçoso"
        RESTAURACAO = "restauracao", "Cópia antes da restauração"

    criada_em = models.DateTimeField("iniciada em", default=timezone.now, db_index=True)
    data_backup = models.DateField("dia do backup", db_index=True)
    status = models.CharField("resultado", max_length=16, choices=Status.choices)
    origem = models.CharField("origem", max_length=16, choices=Origem.choices)
    forcado = models.BooleanField("forçado", default=False)
    caminho = models.CharField("caminho", max_length=1024, blank=True)
    tamanho_bytes = models.PositiveBigIntegerField("tamanho em bytes", null=True, blank=True)
    mensagem = models.TextField("mensagem", blank=True)

    class Meta:
        ordering = ("-criada_em", "-pk")
        verbose_name = "tentativa de backup"
        verbose_name_plural = "tentativas de backup"

    def __str__(self):
        return f"{self.data_backup:%Y-%m-%d} · {self.get_status_display()}"
