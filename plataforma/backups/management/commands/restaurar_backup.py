import getpass

from django.contrib.auth import authenticate
from django.core.management.base import BaseCommand, CommandError

from backups.services import ErroBackup, restaurar_backup


class Command(BaseCommand):
    help = "Restaura o banco a partir de um backup SQLite (pare antes o servidor Django)."

    def add_arguments(self, parser):
        parser.add_argument("arquivo", help="Nome do arquivo dentro da pasta configurada de backups.")
        parser.add_argument("--confirmar-data", required=True, help="Data YYYY-MM-DD contida no nome do backup.")
        parser.add_argument("--usuario", required=True, help="Login do superusuário que autorizou a restauração.")

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("Pare todos os processos do servidor Django antes de restaurar."))
        senha = getpass.getpass("Senha do superusuário: ")
        usuario = authenticate(username=options["usuario"], password=senha)
        if usuario is None or not usuario.is_superuser:
            raise CommandError("A restauração exige credenciais válidas de um superusuário.")
        try:
            resultado = restaurar_backup(options["arquivo"], options["confirmar_data"])
        except ErroBackup as erro:
            raise CommandError(str(erro)) from erro
        self.stdout.write(self.style.SUCCESS(f"Banco restaurado de {resultado.caminho}."))
        self.stdout.write(f"Cópia do estado anterior: {resultado.backup_seguranca}")
