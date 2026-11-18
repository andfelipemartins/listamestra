from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.contrib.auth import views as auth_views
from django.urls import include, path

from contas.views import InicioView
from importacoes.views import ImportarIDView, ImportarSituacaoPWView, LinhasRecusadasView

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "contas/login/",
        auth_views.LoginView.as_view(template_name="contas/login.html"),
        name="login",
    ),
    path(
        "contas/logout/",
        login_required(auth_views.LogoutView.as_view()),
        name="logout",
    ),
    path("importacoes/id/", ImportarIDView.as_view(), name="importar_id"),
    path("importacoes/situacao-pw/", ImportarSituacaoPWView.as_view(), name="importar_situacao_pw"),
    path("importacoes/recusadas/<int:contrato_id>/", LinhasRecusadasView.as_view(), name="linhas_recusadas"),
    path("painel/", include("painel.urls")),
    path("", InicioView.as_view(), name="inicio"),
]
