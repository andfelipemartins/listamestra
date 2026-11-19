import calendar
import re

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from simple_history.models import HistoricalRecords

from contas.models import Usuario
from core.perfil import ErroPerfil, perfil_de_dict


class Contrato(models.Model):
    nome = models.CharField("nome", max_length=200)
    codigo_interno = models.CharField("código interno", max_length=100)
    cliente = models.CharField("cliente", max_length=200)
    descricao = models.TextField("descrição", blank=True)
    ativo = models.BooleanField("ativo", default=True)
    pin_painel = models.CharField("PIN do painel (hash)", max_length=128, blank=True, default="")
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "contrato"
        verbose_name_plural = "contratos"
        ordering = ("nome",)

    def __str__(self):
        return f"{self.codigo_interno} — {self.nome}"

    def definir_pin_painel(self, pin):
        if not isinstance(pin, str) or not re.fullmatch(r"\d{4,6}", pin):
            raise ValidationError({"pin_painel": "O PIN deve ter de 4 a 6 dígitos."})
        self.pin_painel = make_password(pin)

    def verificar_pin_painel(self, pin):
        return bool(self.pin_painel and check_password(pin, self.pin_painel))


class PerfilContrato(models.Model):
    contrato = models.ForeignKey(
        Contrato,
        verbose_name="contrato",
        on_delete=models.CASCADE,
        related_name="perfis",
    )
    versao = models.PositiveIntegerField("versão")
    vigencia_inicio = models.DateField("início da vigência")
    definicao = models.JSONField("definição do perfil", default=dict)
    ativo = models.BooleanField("ativo", default=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "perfil do contrato"
        verbose_name_plural = "perfis do contrato"
        ordering = ("contrato", "-versao")
        constraints = [
            models.UniqueConstraint(
                fields=("contrato", "versao"),
                name="perfil_contrato_versao_unica",
            ),
        ]

    def __str__(self):
        return f"{self.contrato} — v{self.versao}"

    def clean(self):
        super().clean()
        try:
            perfil_de_dict(self.definicao)
        except ErroPerfil as erro:
            raise ValidationError({"definicao": str(erro)}) from erro

    @classmethod
    def perfil_vigente(cls, contrato, data):
        """Retorna o perfil ativo de maior vigência iniciada até a data informada."""
        return (
            cls.objects.filter(
                contrato=contrato,
                ativo=True,
                vigencia_inicio__lte=data,
            )
            .order_by("-vigencia_inicio", "-versao")
            .first()
        )


class FeriadoAcervo(models.Model):
    class Abrangencia(models.TextChoices):
        ESTADUAL = "estadual", "Estadual"
        MUNICIPAL = "municipal", "Municipal"

    class TipoRegra(models.TextChoices):
        FIXA = "fixa", "Data fixa anual"
        PASCOA = "pascoa", "Móvel relativa à Páscoa"

    nome = models.CharField("nome", max_length=200)
    abrangencia = models.CharField(
        "abrangência", max_length=16, choices=Abrangencia.choices
    )
    uf = models.CharField("UF", max_length=2)
    municipio = models.CharField("município", max_length=120, blank=True, default="")
    tipo_regra = models.CharField("regra", max_length=8, choices=TipoRegra.choices)
    dia = models.PositiveSmallIntegerField("dia", null=True, blank=True)
    mes = models.PositiveSmallIntegerField("mês", null=True, blank=True)
    deslocamento_pascoa = models.IntegerField(
        "deslocamento em relação à Páscoa", null=True, blank=True
    )
    vigencia_de = models.PositiveSmallIntegerField(
        "vigente a partir do ano", null=True, blank=True
    )
    vigencia_ate = models.PositiveSmallIntegerField(
        "vigente até o ano", null=True, blank=True
    )
    history = HistoricalRecords()

    class Meta:
        verbose_name = "feriado do acervo"
        verbose_name_plural = "acervo de feriados"
        ordering = ("uf", "municipio", "nome")
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(abrangencia="municipal", municipio__gt="")
                    | Q(abrangencia="estadual", municipio="")
                ),
                name="feriado_acervo_regiao_coerente",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        tipo_regra="fixa",
                        dia__isnull=False,
                        mes__isnull=False,
                        deslocamento_pascoa__isnull=True,
                    )
                    | Q(
                        tipo_regra="pascoa",
                        dia__isnull=True,
                        mes__isnull=True,
                        deslocamento_pascoa__isnull=False,
                    )
                ),
                name="feriado_acervo_regra_coerente",
            ),
            models.CheckConstraint(
                condition=(
                    Q(vigencia_de__isnull=True)
                    | Q(vigencia_ate__isnull=True)
                    | Q(vigencia_de__lte=F("vigencia_ate"))
                ),
                name="feriado_acervo_vigencia_coerente",
            ),
        ]

    def __str__(self):
        return f"{self.nome} ({self.uf})"

    def clean(self):
        super().clean()
        erros = {}
        self.uf = (self.uf or "").strip().upper()
        self.municipio = (self.municipio or "").strip()
        if not re.fullmatch(r"[A-Z]{2}", self.uf):
            erros["uf"] = "Informe uma UF com duas letras."
        if self.abrangencia == self.Abrangencia.MUNICIPAL and not self.municipio:
            erros["municipio"] = "Informe o município para feriados municipais."
        elif self.abrangencia == self.Abrangencia.ESTADUAL and self.municipio:
            erros["municipio"] = "Feriados estaduais não devem ter município."

        if self.tipo_regra == self.TipoRegra.FIXA:
            if self.dia is None or self.mes is None:
                erros["dia"] = "Informe dia e mês para uma data fixa anual."
            elif (
                not 1 <= self.mes <= 12
                or not 1 <= self.dia <= calendar.monthrange(2000, self.mes)[1]
            ):
                erros["dia"] = "Informe um dia e mês válidos."
            if self.deslocamento_pascoa is not None:
                erros["deslocamento_pascoa"] = "Data fixa não deve ter deslocamento da Páscoa."
        elif self.tipo_regra == self.TipoRegra.PASCOA:
            if self.deslocamento_pascoa is None:
                erros["deslocamento_pascoa"] = "Informe o deslocamento em dias da Páscoa."
            if self.dia is not None or self.mes is not None:
                erros["dia"] = "Regra relativa à Páscoa não deve ter dia ou mês fixo."

        if self.vigencia_de is not None and not 1 <= self.vigencia_de <= 9999:
            erros["vigencia_de"] = "O ano de início deve estar entre 1 e 9999."
        if self.vigencia_ate is not None and not 1 <= self.vigencia_ate <= 9999:
            erros["vigencia_ate"] = "O ano final deve estar entre 1 e 9999."
        if (
            self.vigencia_de is not None
            and self.vigencia_ate is not None
            and self.vigencia_de > self.vigencia_ate
        ):
            erros["vigencia_ate"] = "O ano final não pode ser anterior ao ano inicial."
        if erros:
            raise ValidationError(erros)


class Participacao(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuário",
        on_delete=models.CASCADE,
        related_name="participacoes_contratuais",
    )
    contrato = models.ForeignKey(
        Contrato,
        verbose_name="contrato",
        on_delete=models.CASCADE,
        related_name="participacoes",
    )
    papel = models.CharField("papel", max_length=16, choices=Usuario.Perfil.choices)
    ativo = models.BooleanField("ativo", default=True)

    class Meta:
        verbose_name = "participação"
        verbose_name_plural = "participações"
        ordering = ("contrato", "usuario")
        constraints = [
            models.UniqueConstraint(
                fields=("usuario", "contrato"),
                name="participacao_usuario_contrato_unica",
            ),
        ]

    def __str__(self):
        return f"{self.usuario} — {self.contrato} ({self.get_papel_display()})"
