from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from acoes.services import carregar_minha_mesa


class InicioView(LoginRequiredMixin, TemplateView):
    template_name = "inicio.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto.update(carregar_minha_mesa(self.request.user, self.request.GET.get("contrato")))
        return contexto
