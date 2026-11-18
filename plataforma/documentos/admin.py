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
    fields = ("revisao", "versao", "fase", "data_emissao", "origem")


class AnaliseInline(admin.TabularInline):
    model = Analise
    extra = 0
    show_change_link = True
    fields = ("etapa", "situacao", "data_analise", "documento_retorno", "registrado_por")
    readonly_fields = ("registrado_por",)


@admin.register(Documento)
class DocumentoAdmin(admin.ModelAdmin):
    list_display = ("identificador_base", "titulo", "tipo", "disciplina", "trecho", "contrato", "ativo")
    list_filter = ("ativo", "tipo", "disciplina", "trecho", "contrato")
    search_fields = ("identificador_base", "titulo", "codigos__codigo", "contrato__nome")
    inlines = (CodigoDocumentoInline, EmissaoInline)
    readonly_fields = ("criado_em",)


@admin.register(CodigoDocumento)
class CodigoDocumentoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "documento", "perfil")
    list_filter = ("perfil__contrato",)
    search_fields = ("codigo", "documento__identificador_base", "documento__titulo")


@admin.register(Emissao)
class EmissaoAdmin(admin.ModelAdmin):
    list_display = ("documento", "revisao", "versao", "fase", "data_emissao", "origem")
    list_filter = ("fase", "origem", "data_emissao")
    search_fields = ("documento__identificador_base", "documento__titulo", "revisao")
    inlines = (AnaliseInline,)
    readonly_fields = ("criado_em",)


@admin.register(Analise)
class AnaliseAdmin(admin.ModelAdmin):
    list_display = ("emissao", "etapa", "situacao", "data_analise", "documento_retorno", "registrado_por")
    list_filter = ("etapa", "situacao", "data_analise")
    search_fields = ("emissao__documento__identificador_base", "etapa", "situacao", "documento_retorno")
    readonly_fields = ("registrado_em",)
