from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords

from contas.models import Usuario


class Contrato(models.Model):
    nome = models.CharField("nome", max_length=200)
    codigo_interno = models.CharField("código interno", max_length=100)
    cliente = models.CharField("cliente", max_length=200)
    descricao = models.TextField("descrição", blank=True)
    ativo = models.BooleanField("ativo", default=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "contrato"
        verbose_name_plural = "contratos"
        ordering = ("nome",)

    def __str__(self):
        return f"{self.codigo_interno} — {self.nome}"


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
