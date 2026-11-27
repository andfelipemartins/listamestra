from django.urls import path

from .views import contrato_detalhe, contratos_lista


urlpatterns = [
    path("", contratos_lista, name="contratos_lista"),
    path("<int:contrato_id>/", contrato_detalhe, name="contrato_detalhe"),
]
