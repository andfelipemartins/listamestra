from django.urls import path

from .views import ListaBackupsView, PrepararRestauracaoView

app_name = "backups"

urlpatterns = [
    path("", ListaBackupsView.as_view(), name="lista"),
    path("restaurar/<str:arquivo>/", PrepararRestauracaoView.as_view(), name="restaurar"),
]
