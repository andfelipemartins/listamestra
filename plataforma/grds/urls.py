from django.urls import path

from .views import ConfigurarGrdView, DetalheGrdView, ListaGrdsView, NovaGrdView


app_name = "grds"

urlpatterns = [
    path("", ListaGrdsView.as_view(), name="lista"),
    path("nova/", NovaGrdView.as_view(), name="nova"),
    path("configurar/", ConfigurarGrdView.as_view(), name="configurar"),
    path("<int:contrato_id>/<int:grd_id>/", DetalheGrdView.as_view(), name="detalhe"),
]
