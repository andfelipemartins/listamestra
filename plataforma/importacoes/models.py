from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords

from contratos.models import Contrato
from documentos.models import Documento


class IndiceDocumentos(models.Model):
    class Fonte(models.TextChoices):
        EXCEL_ID = "excel_id", "Excel de atributos do ID"
        EXTRACAO_PW = "extracao_pw", "Extração do ID do PW"

    contrato = models.ForeignKey(
        Contrato,
        verbose_name="contrato",
        on_delete=models.PROTECT,
        related_name="indices_documentos",
    )
    codigo = models.CharField("código do ID", max_length=250)
    revisao = models.CharField("revisão", max_length=100)
    fonte = models.CharField("fonte", max_length=20, choices=Fonte.choices)
    arquivo_nome = models.CharField("nome do arquivo", max_length=255)
    importado_em = models.DateTimeField("importado em")
    importado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="importado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="indices_importados",
    )
    vigente = models.BooleanField("vigente", default=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "índice de documentos"
        verbose_name_plural = "índices de documentos"
        ordering = ("contrato", "fonte", "codigo", "revisao")
        constraints = [
            models.UniqueConstraint(
                fields=("contrato", "fonte", "codigo", "revisao"),
                name="indice_contrato_fonte_codigo_revisao_unico",
            ),
        ]

    def __str__(self):
        return f"{self.codigo} — revisão {self.revisao}"


class ItemPrevisto(models.Model):
    indice = models.ForeignKey(
        IndiceDocumentos,
        verbose_name="índice",
        on_delete=models.CASCADE,
        related_name="itens",
    )
    documento = models.ForeignKey(
        Documento,
        verbose_name="documento",
        on_delete=models.PROTECT,
        related_name="itens_previstos",
    )
    titulo = models.CharField("título no índice", max_length=500, blank=True)
    excluido = models.BooleanField("excluído no índice", default=False)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "item previsto"
        verbose_name_plural = "itens previstos"
        ordering = ("documento__identificador_base",)
        constraints = [
            models.UniqueConstraint(
                fields=("indice", "documento"),
                name="item_previsto_indice_documento_unico",
            ),
        ]

    def __str__(self):
        return f"{self.indice.codigo}: {self.documento.identificador_base}"
