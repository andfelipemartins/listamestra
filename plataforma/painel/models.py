from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords


class FotoPainel(models.Model):
    contrato = models.ForeignKey(
        "contratos.Contrato",
        verbose_name="contrato",
        on_delete=models.CASCADE,
        related_name="fotos_painel",
    )
    data = models.DateField("data da foto")
    numeros = models.JSONField("números", default=dict)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="guardado por",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fotos_painel_guardadas",
    )
    criado_em = models.DateTimeField("guardado em", auto_now=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "foto do Painel"
        verbose_name_plural = "fotos do Painel"
        ordering = ("-data",)
        constraints = [
            models.UniqueConstraint(
                fields=("contrato", "data"),
                name="foto_painel_contrato_data_unica",
            ),
        ]

    def __str__(self):
        return f"{self.contrato} · {self.data:%d/%m/%Y}"

    def save(self, *args, **kwargs):
        if not getattr(self, "_history_user", None):
            self._history_user = self.criado_por
        return super().save(*args, **kwargs)
