from django.urls import path

from .views import MeuPerfilView, SenhaAlteradaView, TrocarSenhaView


urlpatterns = [
    path("meu-perfil/", MeuPerfilView.as_view(), name="meu_perfil"),
    path("senha/", TrocarSenhaView.as_view(), name="senha_alterar"),
    path("senha/alterada/", SenhaAlteradaView.as_view(), name="senha_alterada"),
]
