from django import forms

from contratos.models import Contrato


class GrdForm(forms.Form):
    contrato = forms.ModelChoiceField(queryset=Contrato.objects.none(), label="Contrato")
    data = forms.DateField(label="Data", widget=forms.DateInput(attrs={"type": "date"}))
    destinatario = forms.CharField(label="Destinatário", max_length=200)
    observacao = forms.CharField(
        label="Observação",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    texto_codigos = forms.CharField(
        label="Códigos dos documentos",
        widget=forms.Textarea(attrs={"rows": 12, "placeholder": "Um código por linha"}),
    )

    def __init__(self, *args, contratos, initial=None, **kwargs):
        super().__init__(*args, initial=initial, **kwargs)
        self.fields["contrato"].queryset = contratos
