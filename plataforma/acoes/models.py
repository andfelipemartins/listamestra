from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from contratos.models import Contrato
from documentos.models import Documento


class AcaoPendencia(models.Model):
    class Acao(models.TextChoices):
        IGNORAR = "ignorar", "Ignorar"
        PEDIR_CORRECAO = "pedir_correcao", "Pedir correção ao cliente"
        JA_CORRIGI = "ja_corrigi", "Já corrigi"

    contrato = models.ForeignKey(
        Contrato,
        verbose_name="contrato",
        on_delete=models.PROTECT,
        related_name="acoes_pendencias",
    )
    documento = models.ForeignKey(
        Documento,
        verbose_name="documento",
        on_delete=models.PROTECT,
        related_name="acoes_pendencias",
    )
    tipo_pendencia = models.CharField("tipo da pendência", max_length=120)
    acao = models.CharField("ação", max_length=24, choices=Acao.choices)
    motivo = models.TextField("motivo", blank=True)
    texto_email = models.TextField("texto do e-mail", blank=True)
    situacao_referencia = models.CharField("situação de referência", max_length=120, blank=True)
    revisao_referencia = models.CharField("revisão de referência", max_length=40, blank=True)
    data_referencia = models.DateField("data de referência", null=True, blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuário",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acoes_pendencias",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    resolvida_em = models.DateTimeField("resolvida em", null=True, blank=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "ação sobre pendência"
        verbose_name_plural = "ações sobre pendências"
        ordering = ("-criado_em", "-pk")
        indexes = [
            models.Index(
                fields=("contrato", "documento", "tipo_pendencia", "-criado_em"),
                name="acao_pendencia_recente",
            ),
        ]

    def clean(self):
        super().clean()
        if self.contrato_id and self.documento_id and self.contrato_id != self.documento.contrato_id:
            raise ValidationError({"documento": "O documento precisa pertencer ao contrato da ação."})
        if self.acao == self.Acao.IGNORAR and not self.motivo.strip():
            raise ValidationError({"motivo": "Informe o motivo para ignorar a pendência."})

    def __str__(self):
        return f"{self.documento} — {self.get_acao_display()}"
