from django.urls import path

from .views import (
    CancelarDocumentosView,
    DocumentoPastaView,
    DocumentosListaView,
    ListaMestraView,
    ReativarDocumentosView,
)


urlpatterns = [
    path("", DocumentosListaView.as_view(), name="documentos_lista"),
    path("lista-mestra/", ListaMestraView.as_view(), name="lista_mestra"),
    path(
        "cancelar/<int:contrato_id>/",
        CancelarDocumentosView.as_view(),
        name="documentos_cancelar",
    ),
    path(
        "reativar/<int:contrato_id>/",
        ReativarDocumentosView.as_view(),
        name="documentos_reativar",
    ),
    path(
        "<int:contrato_id>/<int:documento_id>/",
        DocumentoPastaView.as_view(),
        name="documento_pasta",
    ),
]
