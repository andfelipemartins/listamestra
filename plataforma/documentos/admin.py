from django.contrib import admin

from .models import Analise, CodigoDocumento, Documento, Emissao


class CodigoDocumentoInline(admin.TabularInline):
    model = CodigoDocumento
    extra = 0
    show_change_link = True


class EmissaoInline(admin.TabularInline):
    model = Emissao
    extra = 0
    show_change_link = True
    fields = (
        "revisao",
        "versao",
        "fase",
        "data_emissao",
        "origem",
        "motivo_reabertura",
        "motivo_reabertura_obs",
    )


class AnaliseInline(admin.TabularInline):
    model = Analise
    extra = 0
    show_change_link = True
    fields = ("etapa", "situacao", "data_analise", "documento_retorno", "registrado_por")
    readonly_fields = ("registrado_por",)


@admin.register(Documento)
class DocumentoAdmin(admin.ModelAdmin):
    list_display = (
        "identificador_base",
        "titulo",
        "tipo",
        "disciplina",
        "trecho",
        "contrato",
        "ativo",
        "cancelado_em",
        "motivo_cancelamento",
    )
    list_filter = (
        "ativo",
        "tipo",
        "disciplina",
        "trecho",
        "contrato",
        "motivo_cancelamento",
        ("cancelado_em", admin.EmptyFieldListFilter),
    )
    search_fields = ("identificador_base", "titulo", "codigos__codigo", "contrato__nome")
    inlines = (CodigoDocumentoInline, EmissaoInline)
    readonly_fields = ("criado_em", "cancelado_por", "cancelado_em", "observacao_reativacao")
    fields = (
        "contrato",
        "identificador_base",
        "tipo",
        "titulo",
        "disciplina",
        "trecho",
        "atributos",
        "fora_do_id",
        "ativo",
        "cancelado_em",
        "cancelado_por",
        "motivo_cancelamento",
        "motivo_cancelamento_obs",
        "observacao_reativacao",
        "criado_em",
    )


@admin.register(CodigoDocumento)
class CodigoDocumentoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "documento", "perfil")
    list_filter = ("perfil__contrato",)
    search_fields = ("codigo", "documento__identificador_base", "documento__titulo")


@admin.register(Emissao)
class EmissaoAdmin(admin.ModelAdmin):
    list_display = (
        "documento",
        "revisao",
        "versao",
        "fase",
        "data_emissao",
        "origem",
        "motivo_reabertura",
    )
    list_filter = ("fase", "origem", "motivo_reabertura", "data_emissao")
    search_fields = ("documento__identificador_base", "documento__titulo", "revisao")
    inlines = (AnaliseInline,)
    readonly_fields = ("criado_em",)


@admin.register(Analise)
class AnaliseAdmin(admin.ModelAdmin):
    list_display = ("emissao", "etapa", "situacao", "data_analise", "documento_retorno", "registrado_por")
    list_filter = ("etapa", "situacao", "data_analise")
    search_fields = ("emissao__documento__identificador_base", "etapa", "situacao", "documento_retorno")
    readonly_fields = ("registrado_em",)
