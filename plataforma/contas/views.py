from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import TemplateView, UpdateView

from acoes.services import carregar_resumo_inicio
from .forms import MeuPerfilForm


class InicioView(LoginRequiredMixin, TemplateView):
    template_name = "inicio.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto.update(carregar_resumo_inicio(self.request.user, self.request.GET.get("contrato")))
        return contexto


class MeuPerfilView(LoginRequiredMixin, UpdateView):
    form_class = MeuPerfilForm
    template_name = "contas/meu_perfil.html"
    success_url = reverse_lazy("meu_perfil")

    def get_object(self, queryset=None):
        return self.request.user

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["participacoes"] = self.request.user.participacoes_contratuais.select_related(
            "contrato"
        ).all()
        return contexto

    def form_valid(self, form):
        messages.success(self.request, "Seu perfil foi atualizado.")
        return super().form_valid(form)


class TrocarSenhaView(LoginRequiredMixin, auth_views.PasswordChangeView):
    template_name = "contas/trocar_senha.html"
    success_url = reverse_lazy("senha_alterada")


class SenhaAlteradaView(LoginRequiredMixin, auth_views.PasswordChangeDoneView):
    template_name = "contas/senha_alterada.html"
