from django import forms

from .models import Usuario


class MeuPerfilForm(forms.ModelForm):
    first_name = forms.CharField(label="Nome", max_length=150, required=True)
    last_name = forms.CharField(label="Sobrenome", max_length=150, required=True)
    email = forms.EmailField(label="E-mail", required=False)

    class Meta:
        model = Usuario
        fields = ("first_name", "last_name", "email")

