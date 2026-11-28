from string import Formatter

from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from contratos.models import Contrato

from .models import GrdCampoCabecalho, GrdConfiguracao
from .servicos import FORMATOS_COPIA_PADRAO, SEGMENTOS_CODIGO


FORMATOS_COPIA_CHOICES = tuple((item, item) for item in GrdConfiguracao.FORMATOS_COPIA)
SEGMENTOS_CODIGO_CHOICES = tuple(SEGMENTOS_CODIGO)


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

    def __init__(
        self, *args, contratos, configuracao=None, initial=None, **kwargs
    ):
        super().__init__(*args, initial=initial, **kwargs)
        self.fields["contrato"].queryset = contratos
        self.campos_digitados = []
        self.campos_digitados_render = []
        if configuracao:
            for campo in configuracao.campos.filter(
                habilitado=True, fonte=GrdCampoCabecalho.Fonte.DIGITADO
            ):
                nome = f"campo_{campo.pk}"
                self.fields[nome] = forms.CharField(
                    label=campo.rotulo,
                    required=False,
                    max_length=200,
                    initial=(initial or {}).get(nome, ""),
                )
                self.campos_digitados.append(campo)
                self.campos_digitados_render.append(
                    {"pk": campo.pk, "form": self[nome]}
                )


class GrdConfiguracaoForm(forms.ModelForm):
    formatos_copias = forms.MultipleChoiceField(
        label="Colunas de cópias",
        choices=FORMATOS_COPIA_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = GrdConfiguracao
        fields = ("logo", "nome_emitente", "titulo", "formato_numero")
        widgets = {
            "formato_numero": forms.TextInput(
                attrs={"placeholder": "{sigla} {seq:03d}/{ano}"}
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["formatos_copias"].initial = (
            self.instance.formatos_copias or FORMATOS_COPIA_PADRAO
        )

    def clean_formato_numero(self):
        formato = self.cleaned_data["formato_numero"].strip()
        campos = []
        try:
            for _, nome, especificacao, conversao in Formatter().parse(formato):
                if nome is None:
                    continue
                if conversao is not None or nome not in {"sigla", "seq", "ano"}:
                    raise ValueError
                if nome == "seq" and especificacao not in {"", "03d", "02d", "04d"}:
                    raise ValueError
                if nome != "seq" and especificacao:
                    raise ValueError
                campos.append(nome)
        except ValueError as erro:
            raise ValidationError(
                "Use apenas {sigla}, {ano}, {seq} ou um formato numérico como {seq:03d}."
            ) from erro
        if "seq" not in campos:
            raise ValidationError("O formato precisa conter o campo {seq}.")
        try:
            formato.format(sigla="ÁLYA", seq=8, ano=2025)
        except (KeyError, ValueError, IndexError) as erro:
            raise ValidationError("O formato do número é inválido.") from erro
        return formato

    def clean_formatos_copias(self):
        formatos = self.cleaned_data["formatos_copias"]
        if not formatos:
            raise ValidationError("Selecione ao menos uma coluna de cópias.")
        return formatos

    def save(self, commit=True):
        configuracao = super().save(commit=False)
        configuracao.formatos_copias = self.cleaned_data["formatos_copias"]
        if commit:
            configuracao.save()
        return configuracao


class GrdCampoCabecalhoForm(forms.ModelForm):
    segmentos_codigo = forms.MultipleChoiceField(
        label="Partes do código",
        choices=SEGMENTOS_CODIGO_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = GrdCampoCabecalho
        fields = (
            "chave",
            "habilitado",
            "rotulo",
            "fonte",
            "valor_contrato",
            "segmentos_codigo",
            "ordem",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.fields["segmentos_codigo"].initial = self.instance.segmentos_codigo or []

    def clean_chave(self):
        chave = self.cleaned_data.get("chave", "").strip().lower()
        if chave and not chave.replace("-", "").replace("_", "").isalnum():
            raise ValidationError("Use letras, números, hífen ou sublinhado no identificador.")
        return chave

    def clean(self):
        dados = super().clean()
        if dados.get("fonte") == GrdCampoCabecalho.Fonte.CODIGO and not dados.get(
            "segmentos_codigo"
        ):
            self.add_error("segmentos_codigo", "Escolha ao menos uma parte do código.")
        return dados


GrdCampoCabecalhoFormSet = inlineformset_factory(
    GrdConfiguracao,
    GrdCampoCabecalho,
    form=GrdCampoCabecalhoForm,
    extra=2,
    can_delete=True,
    max_num=10,
    validate_max=True,
)
