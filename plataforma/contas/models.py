from django.contrib.auth.models import AbstractUser
from django.db import models


class Usuario(AbstractUser):
    class Perfil(models.TextChoices):
        ADMIN = "admin", "Administrador do contrato"
        EQUIPE = "equipe", "Equipe técnica"
        PROJETISTA = "projetista", "Projetista externo"
        CHEFIA = "chefia", "Chefia / coordenação"

    perfil = models.CharField(
        "perfil",
        max_length=16,
        choices=Perfil.choices,
        default=Perfil.EQUIPE,
    )
    empresa = models.CharField("empresa", max_length=200, blank=True)

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"

    def __str__(self):
        return self.get_full_name() or self.username
