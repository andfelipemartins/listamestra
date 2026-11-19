from django.urls import path

from .views import DocumentoPastaView, DocumentosListaView


urlpatterns = [
    path("", DocumentosListaView.as_view(), name="documentos_lista"),
    path(
        "<int:contrato_id>/<int:documento_id>/",
        DocumentoPastaView.as_view(),
        name="documento_pasta",
    ),
]
