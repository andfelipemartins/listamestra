from django import forms


class ImportarFeriadosForm(forms.Form):
    arquivo = forms.FileField(
        label="Planilha de feriados",
        help_text="Arquivo CSV ou XLSX simples, com as colunas data e nome.",
    )
