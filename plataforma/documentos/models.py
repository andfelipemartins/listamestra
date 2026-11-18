from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from simple_history.models import HistoricalRecords

from contratos.models import Contrato, PerfilContrato


class Documento(models.Model):
    contrato = models.ForeignKey(
        Contrato,
        verbose_name="contrato",
        on_delete=models.PROTECT,
        related_name="documentos",
    )
    identificador_base = models.CharField("identificador base", max_length=200)
    tipo = models.CharField("tipo documental", max_length=80, blank=True)
    titulo = models.CharField("título", max_length=500, blank=True)
    disciplina = models.CharField("disciplina", max_length=100, blank=True)
    trecho = models.CharField("trecho", max_length=100, blank=True)
    atributos = models.JSONField("atributos interpretados", default=dict, blank=True)
    fora_do_id = models.BooleanField("fora do ID", default=False)
    ativo = models.BooleanField("ativo", default=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "documento"
        verbose_name_plural = "documentos"
        ordering = ("identificador_base",)
        constraints = [
            models.UniqueConstraint(
                fields=("contrato", "identificador_base"),
                name="documento_identificador_contrato_unico",
            ),
        ]

    def __str__(self):
        return self.identificador_base


class CodigoDocumento(models.Model):
    documento = models.ForeignKey(
        Documento,
        verbose_name="documento",
        on_delete=models.CASCADE,
        related_name="codigos",
    )
    perfil = models.ForeignKey(
        PerfilContrato,
        verbose_name="perfil do código",
        on_delete=models.PROTECT,
        related_name="codigos_documentais",
    )
    codigo = models.CharField("código", max_length=250)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "código do documento"
        verbose_name_plural = "códigos do documento"
        ordering = ("documento", "perfil")
        constraints = [
            models.UniqueConstraint(
                fields=("perfil", "codigo"),
                name="codigo_perfil_codigo_unico",
            ),
            models.UniqueConstraint(
                fields=("documento", "perfil"),
                name="codigo_documento_perfil_unico",
            ),
        ]

    def clean(self):
        super().clean()
        if self.documento_id and self.perfil_id:
            contrato_documento = self.documento.contrato_id
            contrato_perfil = self.perfil.contrato_id
            if contrato_documento != contrato_perfil:
                raise ValidationError(
                    {"perfil": "O perfil do código deve pertencer ao contrato do documento."}
                )
    def __str__(self):
        return self.codigo


class Emissao(models.Model):
    class Fase(models.TextChoices):
        PRELIMINAR = "preliminar", "Preliminar"
        ORIGINAL = "original", "Original"

    class Origem(models.TextChoices):
        INTERNA = "interna", "Interna"
        PROJETISTA = "projetista", "Projetista"
        CLIENTE = "cliente", "Cliente"

    documento = models.ForeignKey(
        Documento,
        verbose_name="documento",
        on_delete=models.CASCADE,
        related_name="emissoes",
    )
    revisao = models.CharField("revisão", max_length=40)
    versao = models.PositiveIntegerField("versão", null=True, blank=True)
    fase = models.CharField("fase", max_length=16, choices=Fase.choices)
    data_emissao = models.DateField("data de emissão")
    origem = models.CharField("origem", max_length=16, choices=Origem.choices)
    observacao = models.TextField("observação", blank=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="registrado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="emissoes_registradas",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "emissão"
        verbose_name_plural = "emissões"
        ordering = ("documento", "data_emissao", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("documento", "revisao", "versao"),
                name="emissao_documento_revisao_versao_unica",
            ),
            models.UniqueConstraint(
                fields=("documento", "revisao"),
                condition=Q(versao__isnull=True),
                name="emissao_sem_versao_unica",
            ),
        ]

    def __str__(self):
        versao = f" v{self.versao}" if self.versao is not None else ""
        return f"{self.documento} — Rev {self.revisao}{versao}"


class Analise(models.Model):
    class Origem(models.TextChoices):
        MANUAL = "manual", "Manual"
        IMPORTADO_PW = "importado_pw", "Importado do PW"
        DEDUZIDO_PW = "deduzido_pw", "Deduzido do PW"

    emissao = models.ForeignKey(
        Emissao,
        verbose_name="emissão",
        on_delete=models.CASCADE,
        related_name="analises",
    )
    etapa = models.CharField("etapa", max_length=100)
    situacao = models.CharField("situação", max_length=100)
    origem = models.CharField(
        "origem",
        max_length=20,
        choices=Origem.choices,
        default=Origem.MANUAL,
    )
    data_analise = models.DateField("data da análise", null=True, blank=True)
    documento_retorno = models.CharField("documento de retorno", max_length=150, blank=True)
    observacao = models.TextField("observação", blank=True)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="registrado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="analises_registradas",
    )
    registrado_em = models.DateTimeField("registrado em", auto_now_add=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "análise"
        verbose_name_plural = "análises"
        ordering = ("-data_analise", "-registrado_em")

    def __str__(self):
        return f"{self.etapa}: {self.situacao} — {self.emissao}"
