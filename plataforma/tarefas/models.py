from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from simple_history.models import HistoricalRecords

from contratos.models import Contrato, Participacao
from documentos.models import Documento, Emissao


class Equipe(models.Model):
    contrato = models.ForeignKey(
        Contrato,
        verbose_name="contrato",
        on_delete=models.CASCADE,
        related_name="equipes_tarefas",
    )
    nome = models.CharField("nome", max_length=120)
    gestor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="gestor",
        on_delete=models.PROTECT,
        related_name="equipes_geridas",
    )
    membros = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        verbose_name="membros",
        blank=True,
        related_name="equipes_tarefas",
    )
    equipe_mae = models.ForeignKey(
        "self",
        verbose_name="equipe-mãe",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="subequipes",
    )
    criada_em = models.DateTimeField("criada em", auto_now_add=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "equipe de tarefas"
        verbose_name_plural = "equipes de tarefas"
        ordering = ("contrato__nome", "nome", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("contrato", "nome"), name="equipe_tarefa_ct_nome_uq"
            ),
        ]

    def clean(self):
        super().clean()
        erros = {}
        if self.contrato_id and self.gestor_id and not _participa_ativo(
            self.gestor_id, self.contrato_id
        ):
            erros["gestor"] = "O gestor precisa participar ativamente deste contrato."
        if self.equipe_mae_id:
            if self.equipe_mae.contrato_id != self.contrato_id:
                erros["equipe_mae"] = "A equipe-mãe precisa pertencer ao mesmo contrato."
            atual = self.equipe_mae
            while atual is not None:
                if atual.pk == self.pk and self.pk is not None:
                    erros["equipe_mae"] = "A hierarquia de equipes não pode formar um ciclo."
                    break
                atual = atual.equipe_mae
        if erros:
            raise ValidationError(erros)

    def save(self, *args, **kwargs):
        self.nome = self.nome.strip()
        if not self.nome:
            raise ValidationError({"nome": "Informe o nome da equipe."})
        self.full_clean(exclude=("membros",))
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nome} — {self.contrato.codigo_interno}"


class Tarefa(models.Model):
    class Status(models.TextChoices):
        ABERTA = "aberta", "Aberta"
        CONCLUIDA = "concluida", "Concluída"
        CANCELADA = "cancelada", "Cancelada"

    contrato = models.ForeignKey(
        Contrato,
        verbose_name="contrato",
        on_delete=models.PROTECT,
        related_name="tarefas",
    )
    titulo = models.CharField("título", max_length=200)
    descricao = models.TextField("descrição", blank=True)
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="responsável",
        on_delete=models.PROTECT,
        related_name="tarefas_responsavel",
    )
    criada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="criada por",
        on_delete=models.PROTECT,
        related_name="tarefas_criadas",
    )
    prazo = models.DateField("prazo")
    documento = models.ForeignKey(
        Documento,
        verbose_name="documento relacionado",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="tarefas",
    )
    status = models.CharField(
        "status", max_length=12, choices=Status.choices, default=Status.ABERTA
    )
    criada_em = models.DateTimeField("criada em", auto_now_add=True)
    concluida_em = models.DateTimeField("concluída em", null=True, blank=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "tarefa"
        verbose_name_plural = "tarefas"
        ordering = ("prazo", "pk")
        indexes = [
            models.Index(fields=("contrato", "status", "prazo"), name="tarefa_ct_status_prazo"),
            models.Index(fields=("contrato", "responsavel", "status"), name="tarefa_ct_resp_status"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=("aberta", "concluida", "cancelada")),
                name="tarefa_status_valido",
            ),
            models.CheckConstraint(
                condition=(Q(status="concluida", concluida_em__isnull=False)
                           | (~Q(status="concluida") & Q(concluida_em__isnull=True))),
                name="tarefa_data_conclusao_coerente",
            ),
        ]

    def clean(self):
        super().clean()
        erros = {}
        if self.documento_id and self.contrato_id and self.documento.contrato_id != self.contrato_id:
            erros["documento"] = "O documento precisa pertencer ao contrato da tarefa."
        if self.status == self.Status.CONCLUIDA and not self.concluida_em:
            erros["concluida_em"] = "Informe quando a tarefa foi concluída."
        if self.status != self.Status.CONCLUIDA and self.concluida_em:
            erros["concluida_em"] = "Somente tarefas concluídas podem ter data de conclusão."
        if erros:
            raise ValidationError(erros)

    @property
    def parece_feita(self):
        if self.status != self.Status.ABERTA or not self.documento_id:
            return False
        if hasattr(self, "_emissao_nova"):
            return self._emissao_nova
        return Emissao.objects.filter(
            documento_id=self.documento_id, criado_em__gt=self.criada_em
        ).exists()

    @property
    def atrasada(self):
        return self.status == self.Status.ABERTA and self.prazo < timezone.localdate()

    def __str__(self):
        return self.titulo


def _participa_ativo(usuario_id, contrato_id):
    return Participacao.objects.filter(
        usuario_id=usuario_id, contrato_id=contrato_id, ativo=True
    ).exists()
