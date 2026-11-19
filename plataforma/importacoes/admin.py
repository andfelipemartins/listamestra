from django.contrib import admin

from .models import (
    ImportacaoID,
    ImportacaoCronograma,
    ImportacaoSituacao,
    InconsistenciaImportacao,
    IndiceDocumentos,
    ItemPrevisto,
    PrevisaoEmissao,
)


class ItemPrevistoInline(admin.TabularInline):
    model = ItemPrevisto
    extra = 0
    show_change_link = True


@admin.register(IndiceDocumentos)
class IndiceDocumentosAdmin(admin.ModelAdmin):
    list_display = (
        "codigo",
        "revisao",
        "fase",
        "escopo",
        "conta_no_previsto",
        "fonte",
        "contrato",
        "importado_em",
        "vigente",
    )
    list_editable = ("fase", "escopo", "conta_no_previsto")
    list_filter = ("fase", "escopo", "conta_no_previsto", "fonte", "vigente", "contrato")
    search_fields = ("codigo", "arquivo_nome", "contrato__nome")
    readonly_fields = ("importado_em",)
    inlines = (ItemPrevistoInline,)


@admin.register(ItemPrevisto)
class ItemPrevistoAdmin(admin.ModelAdmin):
    list_display = ("documento", "indice", "titulo", "excluido")
    list_filter = ("excluido", "indice__fonte", "indice__contrato")
    search_fields = ("documento__identificador_base", "titulo", "indice__codigo")


@admin.register(ImportacaoID)
class ImportacaoIDAdmin(admin.ModelAdmin):
    list_display = ("contrato", "indice", "arquivo_nome", "importado_em", "linhas_validas", "linhas_invalidas")
    list_filter = ("contrato", "importado_em")
    search_fields = ("arquivo_nome", "indice__codigo")
    readonly_fields = tuple(field.name for field in ImportacaoID._meta.fields)


@admin.register(ImportacaoSituacao)
class ImportacaoSituacaoAdmin(admin.ModelAdmin):
    list_display = ("contrato", "data_extracao", "arquivo_nome", "importado_em", "documentos", "emissoes")
    list_filter = ("contrato", "data_extracao")
    search_fields = ("arquivo_nome",)
    readonly_fields = tuple(field.name for field in ImportacaoSituacao._meta.fields)


@admin.register(ImportacaoCronograma)
class ImportacaoCronogramaAdmin(admin.ModelAdmin):
    list_display = ("contrato", "arquivo_nome", "importado_em", "importado_por", "linhas_validas", "linhas_recusadas")
    list_filter = ("contrato", "importado_em")
    search_fields = ("arquivo_nome", "contrato__nome")
    readonly_fields = tuple(field.name for field in ImportacaoCronograma._meta.fields)


@admin.register(PrevisaoEmissao)
class PrevisaoEmissaoAdmin(admin.ModelAdmin):
    list_display = ("documento", "contrato", "data_prevista", "importacao", "criado_em")
    list_filter = ("contrato", "data_prevista")
    search_fields = ("documento__identificador_base", "documento__titulo", "importacao__arquivo_nome")
    readonly_fields = ("criado_em",)


@admin.register(InconsistenciaImportacao)
class InconsistenciaImportacaoAdmin(admin.ModelAdmin):
    list_display = ("numero_linha", "codigo_lido", "caixa_falhou", "mensagem")
    search_fields = ("codigo_lido", "caixa_falhou", "mensagem")
    readonly_fields = tuple(field.name for field in InconsistenciaImportacao._meta.fields)
