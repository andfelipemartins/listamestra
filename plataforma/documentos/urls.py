from django.urls import path

from .views import CancelarDocumentosView, DocumentoPastaView, DocumentosListaView


urlpatterns = [
    path("", DocumentosListaView.as_view(), name="documentos_lista"),
    path(
        "cancelar/<int:contrato_id>/",
        CancelarDocumentosView.as_view(),
        name="documentos_cancelar",
    ),
    path(
        "<int:contrato_id>/<int:documento_id>/",
        DocumentoPastaView.as_view(),
        name="documento_pasta",
    ),
]
