from django.contrib import admin

from .forms import EquipeAdminForm
from .models import Equipe


@admin.register(Equipe)
class EquipeAdmin(admin.ModelAdmin):
    form = EquipeAdminForm
    list_display = ("nome", "contrato", "gestor", "equipe_mae")
    list_filter = ("contrato",)
    search_fields = ("nome", "contrato__nome", "gestor__username", "gestor__first_name", "gestor__last_name")
    autocomplete_fields = ("gestor", "membros", "equipe_mae")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("contrato", "gestor", "equipe_mae")
