import re

from django import forms

from contas.models import Usuario

from .models import Contrato, FeriadoAcervo, Participacao


class ContratoDadosForm(forms.ModelForm):
    regiao_uf = forms.ChoiceField(label="UF da região", required=False)
    regiao_municipio = forms.ChoiceField(label="Município", required=False)

    class Meta:
        model = Contrato
        fields = (
            "codigo_interno",
            "nome",
            "cliente",
            "regiao_uf",
            "regiao_municipio",
            "ativo",
        )
        widgets = {"ativo": forms.CheckboxInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ufs = list(
            FeriadoAcervo.objects.order_by("uf")
            .values_list("uf", flat=True)
            .distinct()
        )
        uf = (
            self.data.get(self.add_prefix("regiao_uf"), "")
            if self.is_bound
            else self.initial.get("regiao_uf", "")
        )
        municipios = list(
            FeriadoAcervo.objects.filter(
                abrangencia=FeriadoAcervo.Abrangencia.MUNICIPAL,
                uf__iexact=uf,
            )
            .order_by("municipio")
            .values_list("municipio", flat=True)
            .distinct()
        )
        self.fields["regiao_uf"].choices = [("", "Selecione")] + [
            (valor, valor) for valor in ufs
        ]
        self.fields["regiao_municipio"].choices = [("", "Selecione")] + [
            (valor, valor) for valor in municipios
        ]

    def clean(self):
        dados = super().clean()
        uf = (dados.get("regiao_uf") or "").strip().upper()
        municipio = (dados.get("regiao_municipio") or "").strip()
        if bool(uf) != bool(municipio):
            self.add_error(
                "regiao_uf",
                "Selecione a UF e o município da região, ou deixe ambos vazios.",
            )
        dados["regiao_uf"] = uf
        dados["regiao_municipio"] = municipio
        return dados


class ParticipacaoForm(forms.Form):
    usuario = forms.ModelChoiceField(
        label="Pessoa cadastrada",
        queryset=Usuario.objects.filter(is_active=True).order_by(
            "first_name", "last_name", "username"
        ),
    )
    papel = forms.ChoiceField(label="Papel", choices=Participacao._meta.get_field("papel").choices)
    funcao = forms.CharField(label="Função", max_length=120, required=False)


class ParticipacaoEdicaoForm(forms.Form):
    papel = forms.ChoiceField(label="Papel", choices=Participacao._meta.get_field("papel").choices)
    funcao = forms.CharField(label="Função", max_length=120, required=False)


class EscopoContratoForm(forms.Form):
    nome = forms.CharField(label="Nome do escopo", max_length=100)
    classes = forms.CharField(
        label="Classes",
        required=False,
        help_text="Separe as classes por vírgula. Exemplos: A, B6, F6.",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def clean_nome(self):
        return self.cleaned_data["nome"].strip()

    def clean_classes(self):
        texto = self.cleaned_data["classes"]
        classes = [item.upper() for item in re.split(r"[,;\s]+", texto) if item.strip()]
        invalidas = [item for item in classes if not re.fullmatch(r"[A-Z](?:\d{1,2})?", item)]
        if invalidas:
            raise forms.ValidationError(
                "Use classes como A, B6 ou F6; valor inválido: %(classe)s.",
                params={"classe": invalidas[0]},
            )
        if len(set(classes)) != len(classes):
            raise forms.ValidationError("A lista contém classes repetidas.")
        return classes


class DiaNaoUtilForm(forms.Form):
    data = forms.DateField(
        label="Data",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    descricao = forms.CharField(label="Descrição", max_length=200)

    def clean_descricao(self):
        return self.cleaned_data["descricao"].strip()


class ImportarFeriadosForm(forms.Form):
    arquivo = forms.FileField(
        label="Planilha de feriados",
        help_text="Arquivo CSV ou XLSX simples, com as colunas data e nome.",
    )
