from django import forms

from documentos.models import Documento

from .models import Equipe, Tarefa


class TarefaForm(forms.ModelForm):
    class Meta:
        model = Tarefa
        fields = ("titulo", "descricao", "responsavel", "prazo", "documento")
        widgets = {
            "descricao": forms.Textarea(attrs={"rows": 4}),
            "prazo": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, contrato, responsaveis, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["responsavel"].queryset = responsaveis
        self.fields["documento"].queryset = Documento.objects.filter(
            contrato=contrato
        ).order_by("identificador_base")
        self.fields["documento"].required = False
        self.fields["documento"].empty_label = "Tarefa livre, sem documento"


class EquipeAdminForm(forms.ModelForm):
    class Meta:
        model = Equipe
        fields = ("contrato", "nome", "gestor", "membros", "equipe_mae")

    def clean(self):
        dados = super().clean()
        contrato = dados.get("contrato")
        usuarios = list(dados.get("membros", ()))
        gestor = dados.get("gestor")
        if contrato:
            from contratos.models import Participacao

            ids_validos = set(
                Participacao.objects.filter(
                    contrato=contrato, ativo=True
                ).values_list("usuario_id", flat=True)
            )
            invalidos = [usuario for usuario in usuarios if usuario.pk not in ids_validos]
            if invalidos:
                self.add_error("membros", "Todos os membros precisam participar do contrato.")
            if gestor and gestor.pk not in ids_validos:
                self.add_error("gestor", "O gestor precisa participar do contrato.")
        return dados
