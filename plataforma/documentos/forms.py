from django import forms


class ColunasListaMestraForm(forms.Form):
    visiveis = forms.MultipleChoiceField(
        label="Colunas visíveis",
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    ordem = forms.CharField(widget=forms.HiddenInput)

    def __init__(self, *, colunas, selecionadas, ordem, data=None):
        super().__init__(data=data)
        self.fields["visiveis"].choices = [
            (coluna["chave"], coluna["rotulo"]) for coluna in colunas
        ]
        self.fields["visiveis"].initial = selecionadas
        self.fields["ordem"].initial = "\n".join(ordem)

    def clean_ordem(self):
        return [chave for chave in self.cleaned_data["ordem"].splitlines() if chave]
