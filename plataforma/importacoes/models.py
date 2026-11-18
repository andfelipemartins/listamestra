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


class ImportacaoID(models.Model):
    contrato = models.ForeignKey(
        Contrato,
        verbose_name="contrato",
        on_delete=models.PROTECT,
        related_name="importacoes_id",
    )
    indice = models.ForeignKey(
        IndiceDocumentos,
        verbose_name="índice",
        on_delete=models.PROTECT,
        related_name="importacoes",
    )
    arquivo_nome = models.CharField("nome do arquivo", max_length=255)
    importado_em = models.DateTimeField("importado em", auto_now_add=True)
    importado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="importado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="importacoes_id",
    )
    linhas_validas = models.PositiveIntegerField("linhas válidas", default=0)
    linhas_invalidas = models.PositiveIntegerField("linhas inválidas", default=0)

    class Meta:
        verbose_name = "importação de ID"
        verbose_name_plural = "importações de ID"
        ordering = ("-importado_em", "-pk")


class ImportacaoSituacao(models.Model):
    contrato = models.ForeignKey(
        Contrato,
        verbose_name="contrato",
        on_delete=models.PROTECT,
        related_name="importacoes_situacao",
    )
    data_extracao = models.DateField("data da extração")
    arquivo_nome = models.CharField("nome do arquivo", max_length=255)
    importado_em = models.DateTimeField("importado em", auto_now_add=True)
    importado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="importado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="importacoes_situacao",
    )
    documentos = models.PositiveIntegerField("documentos", default=0)
    emissoes = models.PositiveIntegerField("emissões", default=0)
    analises_explicitas = models.PositiveIntegerField("análises explícitas", default=0)
    analises_deduzidas = models.PositiveIntegerField("análises deduzidas", default=0)
    historicos_truncados = models.PositiveIntegerField("históricos truncados", default=0)
    fora_do_id = models.PositiveIntegerField("documentos fora do ID", default=0)
    linhas_invalidas = models.PositiveIntegerField("linhas inválidas", default=0)

    class Meta:
        verbose_name = "importação de situação do PW"
        verbose_name_plural = "importações de situação do PW"
        ordering = ("-data_extracao", "-importado_em", "-pk")
        constraints = [
            models.UniqueConstraint(
                fields=("contrato", "data_extracao", "arquivo_nome"),
                name="importacao_situacao_arquivo_data_unica",
            ),
        ]


class InconsistenciaImportacao(models.Model):
    importacao_id = models.ForeignKey(
        ImportacaoID,
        verbose_name="importação de ID",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="inconsistencias",
    )
    importacao_situacao = models.ForeignKey(
        ImportacaoSituacao,
        verbose_name="importação de situação",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="inconsistencias",
    )
    numero_linha = models.PositiveIntegerField("número da linha")
    codigo_lido = models.CharField("código lido", max_length=250, blank=True)
    caixa_falhou = models.CharField("caixa que falhou", max_length=120, blank=True)
    mensagem = models.TextField("mensagem")

    class Meta:
        verbose_name = "inconsistência de importação"
        verbose_name_plural = "inconsistências de importação"
        ordering = ("numero_linha", "pk")
        constraints = [
            models.CheckConstraint(
                condition=(
                    (models.Q(importacao_id__isnull=False) & models.Q(importacao_situacao__isnull=True))
                    | (models.Q(importacao_id__isnull=True) & models.Q(importacao_situacao__isnull=False))
                ),
                name="inconsistencia_uma_importacao",
            ),
        ]
