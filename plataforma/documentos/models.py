import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from simple_history.models import HistoricalRecords

from contratos.models import Contrato, PerfilContrato


class EmpresaElaboradora(models.Model):
    contrato = models.ForeignKey(
        Contrato,
        verbose_name="contrato",
        on_delete=models.PROTECT,
        related_name="empresas_elaboradoras",
    )
    nome = models.CharField("nome", max_length=200)
    nome_normalizado = models.CharField("nome normalizado", max_length=200, editable=False)

    class Meta:
        verbose_name = "empresa elaboradora"
        verbose_name_plural = "empresas elaboradoras"
        ordering = ("nome",)
        constraints = [
            models.UniqueConstraint(
                fields=("contrato", "nome_normalizado"),
                name="emp_elab_ct_nome_norm_uq",
            ),
        ]

    @staticmethod
    def normalizar_nome(nome):
        return re.sub(r"\s+", " ", str(nome or "")).strip().casefold()

    def save(self, *args, **kwargs):
        self.nome = re.sub(r"\s+", " ", self.nome or "").strip()
        if not self.nome:
            raise ValidationError({"nome": "Informe o nome da empresa elaboradora."})
        self.nome_normalizado = self.normalizar_nome(self.nome)
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"nome_normalizado"}
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        self.nome = re.sub(r"\s+", " ", self.nome or "").strip()
        self.nome_normalizado = self.normalizar_nome(self.nome)
        if not self.nome:
            raise ValidationError({"nome": "Informe o nome da empresa elaboradora."})

    def __str__(self):
        return self.nome


class ListaMestraConfiguracao(models.Model):
    contrato = models.OneToOneField(
        Contrato,
        verbose_name="contrato",
        on_delete=models.CASCADE,
        related_name="configuracao_lista_mestra",
    )
    chaves_visiveis = models.JSONField("colunas visíveis", default=list, blank=True)
    chaves_catalogo = models.JSONField("colunas conhecidas", default=list, blank=True)

    class Meta:
        verbose_name = "configuração da Lista Mestra"
        verbose_name_plural = "configurações da Lista Mestra"

    def __str__(self):
        return f"Colunas da Lista Mestra — {self.contrato}"


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
    elaborado_por = models.ForeignKey(
        EmpresaElaboradora,
        verbose_name="elaborado por",
        on_delete=models.SET_NULL,
        related_name="documentos_elaborados",
        null=True,
        blank=True,
    )
    trecho = models.CharField("trecho", max_length=100, blank=True)
    atributos = models.JSONField("atributos interpretados", default=dict, blank=True)
    fora_do_id = models.BooleanField("fora do ID", default=False)
    ativo = models.BooleanField("ativo", default=True)
    cancelado_em = models.DateTimeField("cancelado em", null=True, blank=True)
    cancelado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="cancelado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documentos_cancelados",
    )
    motivo_cancelamento = models.CharField(
        "motivo do cancelamento",
        max_length=50,
        blank=True,
        default="",
    )
    motivo_cancelamento_obs = models.CharField(
        "observação do cancelamento",
        max_length=1000,
        blank=True,
        default="",
    )
    observacao_reativacao = models.CharField(
        "observação da reativação",
        max_length=1000,
        blank=True,
        default="",
    )
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

    def clean(self):
        super().clean()
        if (
            self.elaborado_por_id
            and self.contrato_id
            and self.elaborado_por.contrato_id != self.contrato_id
        ):
            raise ValidationError(
                {"elaborado_por": "A empresa elaboradora deve pertencer ao contrato do documento."}
            )


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

    class MotivoReabertura(models.TextChoices):
        CAMPO = "campo", "Problema de campo"
        PROJETO = "projeto", "Erro de projeto"
        CLIENTE = "cliente", "Pedido do cliente"
        OUTRO = "outro", "Outro"

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
    grd_anterior = models.CharField(
        "GRD anterior ao sistema",
        max_length=200,
        blank=True,
        default="",
    )
    motivo_reabertura = models.CharField(
        "motivo da reabertura",
        max_length=20,
        choices=MotivoReabertura.choices,
        blank=True,
        default="",
    )
    motivo_reabertura_obs = models.CharField(
        "observação do motivo da reabertura",
        max_length=300,
        blank=True,
        default="",
    )
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

    def clean(self):
        super().clean()
        motivo = (self.motivo_reabertura or "").strip()
        observacao = (self.motivo_reabertura_obs or "").strip()
        if not motivo and not observacao:
            return

        erros = {}
        if observacao and motivo != self.MotivoReabertura.OUTRO:
            erros["motivo_reabertura_obs"] = "A observação só pode ser informada para o motivo Outro."
        if self.documento_id:
            from .servicos import _emissao_eh_primeira_reabertura

            if not _emissao_eh_primeira_reabertura(self):
                erros["motivo_reabertura"] = "O motivo só pode ser informado na primeira emissão de uma reabertura."
        else:
            erros["motivo_reabertura"] = "O motivo exige uma emissão vinculada a uma reabertura."
        if erros:
            raise ValidationError(erros)

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
