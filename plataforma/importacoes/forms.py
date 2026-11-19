from django import forms
from django.utils import timezone

from contratos.models import Contrato


class ImportarIDForm(forms.Form):
    contrato = forms.ModelChoiceField(
        label="Contrato",
        queryset=Contrato.objects.filter(ativo=True).order_by("nome"),
    )
    arquivo = forms.FileField(label="Arquivo Excel (.xlsx)")
    codigo_id = forms.CharField(label="Código do ID", max_length=250, required=False)
    revisao = forms.CharField(label="Revisão", max_length=100, required=False)
    fase = forms.CharField(label="Fase", max_length=100, required=False)
    escopo = forms.CharField(
        label="O que este ID representa",
        max_length=100,
        required=False,
        help_text=(
            "Ex.: ID 1001 = Arquitetura e civil; ID 1002 = Sistemas; um ID futuro pode ser de Qualidade; "
            "ID 1501 = fase 2 com tudo."
        ),
    )

    def clean_arquivo(self):
        arquivo = self.cleaned_data["arquivo"]
        if not arquivo.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Envie um arquivo .xlsx.")
        return arquivo


class ImportarSituacaoPWForm(forms.Form):
    contrato = forms.ModelChoiceField(
        label="Contrato",
        queryset=Contrato.objects.filter(ativo=True).order_by("nome"),
    )
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


class ImportarCronogramaForm(forms.Form):
    contrato = forms.ModelChoiceField(
        label="Contrato",
        queryset=Contrato.objects.filter(ativo=True).order_by("nome"),
    )
    arquivo = forms.FileField(label="Cronograma (.xlsx ou .csv)")

    def clean_arquivo(self):
        arquivo = self.cleaned_data["arquivo"]
        if not arquivo.name.lower().endswith((".xlsx", ".csv")):
            raise forms.ValidationError("Envie um arquivo .xlsx ou .csv.")
        return arquivo
