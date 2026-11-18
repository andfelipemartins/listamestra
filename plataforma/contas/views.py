from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView


class InicioView(LoginRequiredMixin, TemplateView):
    template_name = "inicio.html"
