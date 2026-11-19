from django.urls import path

from .views import AcaoView, IgnoradosView, JanelaView, ReativarView

app_name = "acoes"

urlpatterns = [
    path("ignorados/", IgnoradosView.as_view(), name="ignorados"),
    path("acao/", AcaoView.as_view(), name="registrar_acao"),
    path("reativar/", ReativarView.as_view(), name="reativar"),
    path("<slug:tipo>/", JanelaView.as_view(), name="janela"),
]
