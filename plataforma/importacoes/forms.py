from django import forms
from django.utils import timezone

from contratos.models import EscopoContrato
from .models import IndiceDocumentos


class ImportarIDForm(forms.Form):
    arquivo = forms.FileField(label="Arquivo Excel (.xlsx)")
    substituidos = forms.ModelMultipleChoiceField(
        label="Este ID substitui",
        queryset=IndiceDocumentos.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text=(
            "Use somente quando este ID substituir outro código vigente (por exemplo, 1501 → 2000). "
            "Uma nova importação do mesmo código atualiza o ID vigente automaticamente."
        ),
    )
    codigo_id = forms.CharField(label="Código do ID", max_length=250, required=False)
    revisao = forms.CharField(label="Revisão", max_length=100, required=False)
    fase = forms.CharField(label="Fase", max_length=100, required=False)
    escopos = forms.ModelMultipleChoiceField(
        label="Escopos deste ID",
        queryset=EscopoContrato.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Marque todos os escopos do contrato que este ID representa.",
    )
    novo_escopo = forms.CharField(
        label="+ novo escopo",
        max_length=100,
        required=False,
        help_text="Se já existir neste contrato, será reutilizado.",
    )

    def __init__(self, *args, contrato=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.contrato = contrato
        if contrato:
            self.fields["escopos"].queryset = EscopoContrato.objects.filter(
                contrato=contrato
            ).order_by("nome")
            self.fields["substituidos"].queryset = IndiceDocumentos.objects.filter(
                contrato=contrato,
                fonte=IndiceDocumentos.Fonte.EXCEL_ID,
                vigente=True,
            ).order_by("codigo", "revisao")

    def clean_substituidos(self):
        indices = self.cleaned_data["substituidos"]
        if self.contrato and any(
            indice.contrato_id != self.contrato.pk
            or indice.fonte != IndiceDocumentos.Fonte.EXCEL_ID
            or not indice.vigente
            for indice in indices
        ):
            raise forms.ValidationError(
                "Selecione apenas IDs vigentes de Excel do contrato ativo."
            )
        return indices

    def clean_escopos(self):
        escopos = self.cleaned_data["escopos"]
        if self.contrato and any(
            escopo.contrato_id != self.contrato.pk for escopo in escopos
        ):
            raise forms.ValidationError(
                "Selecione apenas escopos cadastrados para o contrato ativo."
            )
        return escopos

    def clean_novo_escopo(self):
        return self.cleaned_data["novo_escopo"].strip()

    def clean_arquivo(self):
        arquivo = self.cleaned_data["arquivo"]
        if not arquivo.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Envie um arquivo .xlsx.")
        return arquivo


class ImportarSituacaoPWForm(forms.Form):
    arquivo = forms.FileField(label="Extração de situação do PW (.xlsx)")
    data_extracao = forms.DateField(
        label="Data da extração",
        initial=timezone.localdate,
        input_formats=("%Y-%m-%d", "%d/%m/%Y"),
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def clean_arquivo(self):
        arquivo = self.cleaned_data["arquivo"]
        if not arquivo.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Envie um arquivo .xlsx.")
        return arquivo


class ImportarSituacaoPadraoForm(forms.Form):
    arquivo = forms.FileField(label="Planilha de situação (.xlsx ou .csv)")

    def clean_arquivo(self):
        arquivo = self.cleaned_data["arquivo"]
        if not arquivo.name.lower().endswith((".xlsx", ".csv")):
            raise forms.ValidationError("Envie um arquivo .xlsx ou .csv.")
        return arquivo


class ImportarCronogramaForm(forms.Form):
    arquivo = forms.FileField(label="Cronograma (.xlsx ou .csv)")

    def clean_arquivo(self):
        arquivo = self.cleaned_data["arquivo"]
        if not arquivo.name.lower().endswith((".xlsx", ".csv")):
            raise forms.ValidationError("Envie um arquivo .xlsx ou .csv.")
        return arquivo


class ImportarElaboracaoForm(forms.Form):
    arquivo = forms.FileField(label="Lista Mestra (.xlsx ou .xlsm)")

    def clean_arquivo(self):
        arquivo = self.cleaned_data["arquivo"]
        if not arquivo.name.lower().endswith((".xlsx", ".xlsm")):
            raise forms.ValidationError("Envie um arquivo .xlsx ou .xlsm.")
        return arquivo
