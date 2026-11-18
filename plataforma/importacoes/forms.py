from django import forms

from contratos.models import Contrato


class ImportarIDForm(forms.Form):
    contrato = forms.ModelChoiceField(
        label="Contrato",
        queryset=Contrato.objects.filter(ativo=True).order_by("nome"),
    )
    arquivo = forms.FileField(label="Arquivo Excel (.xlsx)")
    codigo_id = forms.CharField(label="Código do ID", max_length=250, required=False)
    revisao = forms.CharField(label="Revisão", max_length=100, required=False)

    def clean_arquivo(self):
        arquivo = self.cleaned_data["arquivo"]
        if not arquivo.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Envie um arquivo .xlsx.")
        return arquivo
