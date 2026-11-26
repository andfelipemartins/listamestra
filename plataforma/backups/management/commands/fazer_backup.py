from django.core.management.base import BaseCommand, CommandError

from backups.services import fazer_backup


class Command(BaseCommand):
    help = "Cria a cópia diária completa do banco de dados."

    def add_arguments(self, parser):
        parser.add_argument("--forcar", action="store_true", help="Cria outra cópia mesmo que já exista uma hoje.")

    def handle(self, *args, **options):
        resultado = fazer_backup(force=options["forcar"])
        if not resultado.sucesso:
            self.stderr.write(self.style.ERROR(f"Falha no backup: {resultado.mensagem}"))
            raise CommandError(resultado.mensagem)
        if resultado.ignorado:
            self.stdout.write(self.style.WARNING(resultado.mensagem))
            return
        self.stdout.write(self.style.SUCCESS(f"Backup criado: {resultado.caminho} ({resultado.tamanho_bytes} bytes)"))
