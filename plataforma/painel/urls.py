from django.urls import path

from .views import PainelRecorteView, PainelView, ResumoExecutivoView

urlpatterns = [
    path("<int:contrato_id>/", PainelView.as_view(), name="painel"),
    path(
        "<int:contrato_id>/resumo-executivo/",
        ResumoExecutivoView.as_view(),
        name="resumo_executivo",
    ),
    path("<int:contrato_id>/recorte/", PainelRecorteView.as_view(), name="painel_recorte"),
]
