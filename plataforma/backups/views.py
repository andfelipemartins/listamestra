from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.utils.dateparse import parse_date
from django.views.generic import TemplateView

from .services import caminho_de_backup, listar_backups


class AdminPlataformaMixin(LoginRequiredMixin, UserPassesTestMixin):
    raise_exception = True

    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser


class ListaBackupsView(AdminPlataformaMixin, TemplateView):
    template_name = "backups/lista.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto.update(
            backups=listar_backups(),
            pasta_backup=str(settings.SCLME_BACKUP_DIR),
            pode_restaurar=self.request.user.is_superuser,
        )
        return contexto


class PrepararRestauracaoView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = "backups/restaurar.html"
    raise_exception = True

    def test_func(self):
        return self.request.user.is_superuser

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto.update(arquivo=self.kwargs["arquivo"], erro="", comando="")
        caminho = caminho_de_backup(contexto["arquivo"])
        data_do_nome = contexto["arquivo"][6:16] if caminho else ""
        contexto["data_backup"] = parse_date(data_do_nome) if data_do_nome else None
        return contexto

    def post(self, request, *args, **kwargs):
        contexto = self.get_context_data(**kwargs)
        arquivo = contexto["arquivo"]
        caminho = caminho_de_backup(arquivo)
        confirmacao = request.POST.get("confirmacao", "").strip()
        data_confirmacao = contexto["data_backup"].isoformat() if contexto["data_backup"] else ""
        if caminho is None:
            contexto["erro"] = "O arquivo de backup não foi encontrado."
        elif confirmacao != data_confirmacao:
            contexto["erro"] = f"Digite exatamente {data_confirmacao} para confirmar."
        else:
            usuario = self.request.user.get_username().replace("'", "''")
            contexto["comando"] = (
                f'..\\.venv\\Scripts\\python.exe manage.py restaurar_backup "{arquivo}" '
                f"--confirmar-data {data_confirmacao} --usuario '{usuario}'"
            )
        return self.render_to_response(contexto)
