from django.urls import path

from .views import (
    FotosPainelView,
    GuardarFotoPainelView,
    PainelRecorteView,
    PainelView,
    ResumoExecutivoView,
)

urlpatterns = [
    path("<int:contrato_id>/", PainelView.as_view(), name="painel"),
    path(
        "<int:contrato_id>/resumo-executivo/",
        ResumoExecutivoView.as_view(),
        name="resumo_executivo",
    ),
    path("<int:contrato_id>/fotos/", FotosPainelView.as_view(), name="painel_fotos"),
    path(
        "<int:contrato_id>/fotos/guardar/",
        GuardarFotoPainelView.as_view(),
        name="painel_guardar_foto",
    ),
    path("<int:contrato_id>/recorte/", PainelRecorteView.as_view(), name="painel_recorte"),
]
