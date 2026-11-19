from django.urls import path

from .views import AtividadeView


urlpatterns = [path("", AtividadeView.as_view(), name="atividade")]
