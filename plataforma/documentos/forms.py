from django import forms

from .models import ColunaPersonalizada


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


class ColunaPersonalizadaForm(forms.Form):
    nome = forms.CharField(label="Nome", max_length=120)
    tipo = forms.ChoiceField(label="Tipo", choices=ColunaPersonalizada.Tipo.choices)
    nivel = forms.ChoiceField(label="Nível", choices=ColunaPersonalizada.Nivel.choices)
    opcoes = forms.CharField(
        label="Opções, uma por linha",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
    )

    def __init__(self, *, instance=None, data=None):
        super().__init__(data=data)
        self.instance = instance
        if instance is None:
            return
        self.fields.pop("tipo")
        self.fields.pop("nivel")
        self.fields["nome"].initial = instance.nome
        self.fields["opcoes"].initial = "\n".join(instance.opcoes or [])

    def clean_nome(self):
        return " ".join(self.cleaned_data["nome"].split())

    def clean_opcoes(self):
        linhas = self.cleaned_data["opcoes"].splitlines()
        resultado = []
        vistos = set()
        for linha in linhas:
            valor = " ".join(linha.split())
            if valor and valor.casefold() not in vistos:
                resultado.append(valor)
                vistos.add(valor.casefold())
        tipo = self.cleaned_data.get("tipo") or getattr(self.instance, "tipo", "")
        if tipo == ColunaPersonalizada.Tipo.LISTA and not resultado:
            raise forms.ValidationError("Informe ao menos uma opção para a lista.")
        if tipo != ColunaPersonalizada.Tipo.LISTA and resultado:
            raise forms.ValidationError("Opções só podem ser informadas para colunas do tipo lista.")
        return resultado


class ValorColunaPersonalizadaForm(forms.Form):
    motivo = forms.CharField(label="Motivo (obrigatório)", max_length=100)

    def __init__(self, *, coluna, data=None):
        super().__init__(data=data)
        self.coluna = coluna
        self.fields["valor"] = _campo_valor(coluna)


class PreencherLoteColunaForm(forms.Form):
    codigos = forms.CharField(
        label="Códigos, um por linha",
        widget=forms.Textarea(attrs={"rows": 8, "placeholder": "Cole um código por linha"}),
    )
    motivo = forms.CharField(label="Motivo (obrigatório)", max_length=100)
    substituir = forms.BooleanField(
        label="Substituir valores diferentes",
        required=False,
    )

    def __init__(self, *, coluna, data=None):
        super().__init__(data=data)
        self.coluna = coluna
        self.fields["valor"] = _campo_valor(coluna)
        if coluna.nivel == ColunaPersonalizada.Nivel.REVISAO:
            self.fields["revisao"] = forms.CharField(
                label="Revisão a preencher",
                max_length=40,
            )


def _campo_valor(coluna):
    if coluna.tipo == ColunaPersonalizada.Tipo.DATA:
        return forms.DateField(
            label=coluna.nome,
            required=False,
            input_formats=["%Y-%m-%d"],
            widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        )
    if coluna.tipo == ColunaPersonalizada.Tipo.LISTA:
        return forms.ChoiceField(
            label=coluna.nome,
            required=False,
            choices=[("", "—"), *((opcao, opcao) for opcao in coluna.opcoes or [])],
        )
    return forms.CharField(
        label=coluna.nome,
        required=False,
        max_length=2000,
        widget=forms.TextInput(),
    )
