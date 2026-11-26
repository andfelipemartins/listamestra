from django import forms
from django.utils import timezone

from contratos.models import Contrato, EscopoContrato
from .models import IndiceDocumentos


class ImportarIDForm(forms.Form):
    contrato = forms.ModelChoiceField(
        label="Contrato",
        queryset=Contrato.objects.filter(ativo=True).order_by("nome"),
    )
    arquivo = forms.FileField(label="Arquivo Excel (.xlsx)")
    substituidos = forms.ModelMultipleChoiceField(
        label="Este ID substitui",
        queryset=IndiceDocumentos.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text=(
            "Opcional. Marque os IDs vigentes deste contrato que este Excel substitui; "
            "eles permanecem no histórico e deixam de compor o previsto."
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        contrato_id = None
        if self.is_bound:
            contrato_id = self.data.get(self.add_prefix("contrato"))
        else:
            contrato = self.initial.get("contrato")
            contrato_id = getattr(contrato, "pk", contrato)
        if contrato_id:
            self.fields["escopos"].queryset = EscopoContrato.objects.filter(
                contrato_id=contrato_id
            ).order_by("nome")
            self.fields["substituidos"].queryset = IndiceDocumentos.objects.filter(
                contrato_id=contrato_id,
                fonte=IndiceDocumentos.Fonte.EXCEL_ID,
                vigente=True,
            ).order_by("codigo", "revisao")

    def clean_substituidos(self):
        indices = self.cleaned_data["substituidos"]
        contrato = self.cleaned_data.get("contrato")
        if contrato and any(
            indice.contrato_id != contrato.pk
            or indice.fonte != IndiceDocumentos.Fonte.EXCEL_ID
            or not indice.vigente
            for indice in indices
        ):
            raise forms.ValidationError(
                "Selecione apenas IDs vigentes de Excel do contrato escolhido."
            )
        return indices

    def clean_escopos(self):
        escopos = self.cleaned_data["escopos"]
        contrato = self.cleaned_data.get("contrato")
        if contrato and any(escopo.contrato_id != contrato.pk for escopo in escopos):
            raise forms.ValidationError(
                "Selecione apenas escopos cadastrados para o contrato escolhido."
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


class ImportarSituacaoPadraoForm(forms.Form):
    contrato = forms.ModelChoiceField(
        label="Contrato",
        queryset=Contrato.objects.none(),
    )
    arquivo = forms.FileField(label="Planilha de situação (.xlsx ou .csv)")

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        contratos = Contrato.objects.filter(ativo=True)
        if usuario and not usuario.is_staff:
            from contas.models import Usuario
            from contratos.models import Participacao

            ids = Participacao.objects.filter(
                usuario=usuario,
                ativo=True,
                papel__in=(Usuario.Perfil.ADMIN, Usuario.Perfil.EQUIPE),
            ).values_list("contrato_id", flat=True)
            contratos = contratos.filter(pk__in=ids)
        self.fields["contrato"].queryset = contratos.order_by("nome")

    def clean_arquivo(self):
        arquivo = self.cleaned_data["arquivo"]
        if not arquivo.name.lower().endswith((".xlsx", ".csv")):
            raise forms.ValidationError("Envie um arquivo .xlsx ou .csv.")
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
