from django.contrib import admin

from .models import IndiceDocumentos, ItemPrevisto


class ItemPrevistoInline(admin.TabularInline):
    model = ItemPrevisto
    extra = 0
    show_change_link = True


@admin.register(IndiceDocumentos)
class IndiceDocumentosAdmin(admin.ModelAdmin):
    list_display = ("codigo", "revisao", "fonte", "contrato", "importado_em", "vigente")
    list_filter = ("fonte", "vigente", "contrato")
    search_fields = ("codigo", "arquivo_nome", "contrato__nome")
    readonly_fields = ("importado_em",)
    inlines = (ItemPrevistoInline,)


@admin.register(ItemPrevisto)
class ItemPrevistoAdmin(admin.ModelAdmin):
    list_display = ("documento", "indice", "titulo", "excluido")
    list_filter = ("excluido", "indice__fonte", "indice__contrato")
    search_fields = ("documento__identificador_base", "titulo", "indice__codigo")
