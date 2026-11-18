from django.contrib import admin

from .models import Contrato, Participacao, PerfilContrato


class PerfilContratoInline(admin.TabularInline):
    model = PerfilContrato
    extra = 0
    show_change_link = True


@admin.register(Contrato)
class ContratoAdmin(admin.ModelAdmin):
    list_display = ("nome", "codigo_interno", "cliente", "ativo", "criado_em")
    list_filter = ("ativo", "cliente")
    search_fields = ("nome", "codigo_interno", "cliente", "descricao")
    inlines = (PerfilContratoInline,)
    readonly_fields = ("criado_em",)


@admin.register(PerfilContrato)
class PerfilContratoAdmin(admin.ModelAdmin):
    list_display = ("contrato", "versao", "vigencia_inicio", "ativo", "criado_em")
    list_filter = ("ativo", "contrato")
    search_fields = ("contrato__nome", "contrato__codigo_interno")
    readonly_fields = ("criado_em",)


@admin.register(Participacao)
class ParticipacaoAdmin(admin.ModelAdmin):
    list_display = ("usuario", "contrato", "papel", "ativo")
    list_filter = ("papel", "ativo", "contrato")
    search_fields = ("usuario__username", "usuario__first_name", "usuario__last_name", "contrato__nome")
