from django.urls import path

from .views import (
    TarefaCancelarView,
    TarefaConcluirView,
    TarefaCriarView,
    TarefaDetalheView,
    TarefasListaView,
)


app_name = "tarefas"

urlpatterns = [
    path("", TarefasListaView.as_view(), name="lista"),
    path("nova/", TarefaCriarView.as_view(), name="criar"),
    path("<int:tarefa_id>/", TarefaDetalheView.as_view(), name="detalhe"),
    path("<int:tarefa_id>/concluir/", TarefaConcluirView.as_view(), name="concluir"),
    path("<int:tarefa_id>/cancelar/", TarefaCancelarView.as_view(), name="cancelar"),
]
