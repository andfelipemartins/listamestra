from django.conf import settings
from django.db import models

from contratos.models import Contrato
from documentos.models import Emissao


class Grd(models.Model):
    contrato = models.ForeignKey(
        Contrato,
        verbose_name="contrato",
        on_delete=models.PROTECT,
        related_name="grds",
    )
    numero = models.PositiveIntegerField("número")
    data = models.DateField("data")
    destinatario = models.CharField("destinatário", max_length=200)
    observacao = models.TextField("observação", blank=True, default="")
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="criado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="grds_criadas",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "GRD"
        verbose_name_plural = "GRDs"
        ordering = ("-criado_em", "-numero")
        constraints = [
            models.UniqueConstraint(
                fields=("contrato", "numero"),
                name="grd_numero_unico_por_contrato",
            ),
        ]

    def __str__(self):
        return self.rotulo()

    def rotulo(self):
        return f"GRD-{self.contrato.codigo_interno}-{self.numero:04d}"


class GrdItem(models.Model):
    grd = models.ForeignKey(
        Grd,
        verbose_name="GRD",
        on_delete=models.CASCADE,
        related_name="itens",
    )
    emissao = models.ForeignKey(
        Emissao,
        verbose_name="emissão",
        on_delete=models.PROTECT,
        related_name="itens_grd",
    )

    class Meta:
        verbose_name = "item da GRD"
        verbose_name_plural = "itens da GRD"
        ordering = ("emissao__documento__identificador_base", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("grd", "emissao"),
                name="grd_emissao_unica",
            ),
        ]

    def __str__(self):
        return f"{self.grd.rotulo()} — {self.emissao}"
