from django.contrib import admin

from .models import AcaoPendencia


@admin.register(AcaoPendencia)
class AcaoPendenciaAdmin(admin.ModelAdmin):
    list_display = ("documento", "tipo_pendencia", "acao", "usuario", "criado_em", "resolvida_em")
    list_filter = ("acao", "tipo_pendencia")
    search_fields = ("documento__identificador_base", "motivo", "texto_email")
    readonly_fields = ("criado_em", "resolvida_em")
