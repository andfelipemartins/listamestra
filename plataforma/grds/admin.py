from django.contrib import admin

from .models import Grd, GrdItem


class GrdItemInline(admin.TabularInline):
    model = GrdItem
    extra = 0
    can_delete = False
    fields = ("emissao",)
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Grd)
class GrdAdmin(admin.ModelAdmin):
    list_display = ("rotulo", "contrato", "data", "destinatario", "criado_por", "criado_em")
    list_filter = ("contrato", "data")
    search_fields = ("contrato__codigo_interno", "destinatario")
    readonly_fields = (
        "contrato",
        "numero",
        "data",
        "destinatario",
        "observacao",
        "criado_por",
        "criado_em",
    )
    inlines = (GrdItemInline,)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(GrdItem)
class GrdItemAdmin(admin.ModelAdmin):
    list_display = ("grd", "emissao")
    list_select_related = ("grd", "emissao", "emissao__documento")
    search_fields = ("grd__contrato__codigo_interno", "emissao__documento__identificador_base")
    readonly_fields = ("grd", "emissao")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff

    def has_delete_permission(self, request, obj=None):
        return False
