from django.urls import path

from .views import (
    AbertasView,
    AcaoView,
    AtrasadosLegadoView,
    AtrasadosLadoView,
    AtrasadosView,
    IgnoradosView,
    JanelaView,
    PendenciasView,
    ReativarView,
    UsarTituloIDView,
)

app_name = "acoes"

urlpatterns = [
    path("pendencias/", PendenciasView.as_view(), name="pendencias"),
    path("pendencias/abertas/", AbertasView.as_view(), name="abertas"),
    path("pendencias/atrasados/", AtrasadosView.as_view(), name="atrasados"),
    path("pendencias/atrasados/<slug:lado>/", AtrasadosLadoView.as_view(), name="atrasados_lado"),
    path("atrasados/", AtrasadosLegadoView.as_view(), name="atrasados_legado"),
    path("ignorados/", IgnoradosView.as_view(), name="ignorados"),
    path("acao/", AcaoView.as_view(), name="registrar_acao"),
    path("titulo-id/usar/", UsarTituloIDView.as_view(), name="usar_titulo_id"),
    path("reativar/", ReativarView.as_view(), name="reativar"),
    path("<slug:tipo>/", JanelaView.as_view(), name="janela"),
]
