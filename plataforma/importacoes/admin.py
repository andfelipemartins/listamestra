from django.contrib import admin
from django import forms
from django.core.exceptions import ValidationError

from contratos.models import EscopoContrato
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


class IndiceDocumentosAdminForm(forms.ModelForm):
    class Meta:
        model = IndiceDocumentos
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["escopos"].widget = forms.CheckboxSelectMultiple()
        contrato_id = None
        if self.is_bound:
            contrato_id = self.data.get(self.add_prefix("contrato"))
        elif self.instance and self.instance.pk:
            contrato_id = self.instance.contrato_id
        if contrato_id:
            self.fields["escopos"].queryset = EscopoContrato.objects.filter(
                contrato_id=contrato_id
            ).order_by("nome")
        else:
            self.fields["escopos"].queryset = EscopoContrato.objects.none()

    def clean(self):
        dados = super().clean()
        contrato = dados.get("contrato")
        escopos = dados.get("escopos")
        if contrato and escopos and any(
            escopo.contrato_id != contrato.pk for escopo in escopos
        ):
            raise ValidationError("Um ID só pode receber escopos do mesmo contrato.")
        return dados


@admin.register(IndiceDocumentos)
class IndiceDocumentosAdmin(admin.ModelAdmin):
    form = IndiceDocumentosAdminForm
    list_display = (
        "codigo",
        "revisao",
        "fase",
        "escopos_lista",
        "conta_no_previsto",
        "substituido_por",
        "fonte",
        "contrato",
        "importado_em",
        "vigente",
    )
    list_editable = ("fase", "conta_no_previsto")
    list_filter = ("fase", "escopos", "conta_no_previsto", "fonte", "vigente", "contrato")
    search_fields = ("codigo", "arquivo_nome", "contrato__nome")
    readonly_fields = ("importado_em", "substituido_por")
    inlines = (ItemPrevistoInline,)

    @admin.display(description="escopos")
    def escopos_lista(self, obj):
        return ", ".join(obj.escopos.values_list("nome", flat=True))


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
