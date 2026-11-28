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
    numero_formatado = models.CharField("número formatado", max_length=160, blank=True, default="")
    data = models.DateField("data")
    destinatario = models.CharField("destinatário", max_length=200)
    observacao = models.TextField("observação", blank=True, default="")
    campos_cabecalho = models.JSONField("campos do cabeçalho", default=dict, blank=True)
    formatos_copias = models.JSONField("colunas de cópias", default=list, blank=True)
    emitido_por_nome = models.CharField("nome de quem emitiu", max_length=200, blank=True, default="")
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
        if self.numero_formatado:
            return self.numero_formatado
        return f"GRD-{self.contrato.codigo_interno}-{self.numero:04d}"


class GrdConfiguracao(models.Model):
    FORMATOS_COPIA = ("A0", "A1", "A2", "A3", "A4", "Digital")

    contrato = models.OneToOneField(
        Contrato,
        verbose_name="contrato",
        on_delete=models.CASCADE,
        related_name="configuracao_grd",
    )
    logo = models.ImageField("logo", upload_to="grds/logos/", blank=True)
    nome_emitente = models.CharField("nome de quem emite", max_length=100, default="ÁLYA")
    titulo = models.CharField(
        "título", max_length=160, default="Guia de Remessa de Documentos"
    )
    formato_numero = models.CharField(
        "formato do número", max_length=160, default="{sigla} {seq:03d}/{ano}"
    )
    formatos_copias = models.JSONField(
        "colunas de cópias", default=list, blank=True
    )

    class Meta:
        verbose_name = "configuração de GRD"
        verbose_name_plural = "configurações de GRD"

    def __str__(self):
        return f"Configuração de GRD — {self.contrato}"


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
    copias = models.JSONField("quantidades de cópias", default=dict, blank=True)

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


class GrdCampoCabecalho(models.Model):
    class Fonte(models.TextChoices):
        CONTRATO = "contrato", "Texto configurado"
        CODIGO = "codigo", "Partes do código documental"
        DIGITADO = "digitado", "Preenchido ao criar a GRD"

    configuracao = models.ForeignKey(
        GrdConfiguracao,
        verbose_name="configuração",
        on_delete=models.CASCADE,
        related_name="campos",
    )
    chave = models.SlugField("identificador", max_length=40)
    habilitado = models.BooleanField("exibir", default=True)
    rotulo = models.CharField("rótulo", max_length=80)
    fonte = models.CharField("fonte", max_length=12, choices=Fonte.choices)
    valor_contrato = models.CharField("texto do contrato", max_length=200, blank=True, default="")
    segmentos_codigo = models.JSONField("segmentos do código", default=list, blank=True)
    ordem = models.PositiveSmallIntegerField("ordem", default=0)

    class Meta:
        verbose_name = "campo do cabeçalho da GRD"
        verbose_name_plural = "campos do cabeçalho da GRD"
        ordering = ("ordem", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("configuracao", "chave"),
                name="grd_campo_chave_unica_config",
            ),
        ]

    def __str__(self):
        return self.rotulo
