from pathlib import Path
from datetime import date, datetime

import yaml
from django.core.management.base import BaseCommand, CommandError

from core.perfil import ErroPerfil, carregar_yaml
from contratos.models import Contrato, PerfilContrato


class Command(BaseCommand):
    help = "Cria um perfil de contrato a partir de um arquivo YAML de exemplo."

    def add_arguments(self, parser):
        parser.add_argument("contrato_id", type=int)
        parser.add_argument("caminho_yaml")
        parser.add_argument("--versao", type=int)

    def handle(self, *args, **options):
        contrato_id = options["contrato_id"]
        try:
            contrato = Contrato.objects.get(pk=contrato_id)
        except Contrato.DoesNotExist as erro:
            raise CommandError(f"Contrato com ID {contrato_id} não existe.") from erro

        caminho = Path(options["caminho_yaml"])
        try:
            perfil_validado = carregar_yaml(caminho)
        except ErroPerfil as erro:
            raise CommandError(f"YAML de perfil inválido: {erro}") from erro

        try:
            with caminho.open("r", encoding="utf-8") as arquivo:
                definicao = _json_compatibility(yaml.safe_load(arquivo))
        except (OSError, yaml.YAMLError) as erro:
            raise CommandError(f"Não foi possível ler o YAML do perfil: {erro}") from erro

        versao = options["versao"]
        if versao is None:
            versao = (
                PerfilContrato.objects.filter(contrato=contrato)
                .order_by("-versao")
                .values_list("versao", flat=True)
                .first()
                or 0
            ) + 1
        if versao < 1:
            raise CommandError("A versão do perfil deve ser um inteiro maior que zero.")
        if PerfilContrato.objects.filter(contrato=contrato, versao=versao).exists():
            raise CommandError(
                f"O contrato {contrato_id} já possui um perfil na versão {versao}."
            )

        perfil = PerfilContrato.objects.create(
            contrato=contrato,
            versao=versao,
            vigencia_inicio=perfil_validado.vigencia_inicio,
            definicao=definicao,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Perfil v{perfil.versao} criado para o contrato {contrato_id} "
                f"({contrato.nome}) a partir de {caminho}."
            )
        )


def _json_compatibility(valor):
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {chave: _json_compatibility(item) for chave, item in valor.items()}
    if isinstance(valor, list):
        return [_json_compatibility(item) for item in valor]
    return valor
