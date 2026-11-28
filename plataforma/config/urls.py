from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.contrib.auth import views as auth_views
from django.urls import include, path

from acoes.views import AtivarContratoView, HomeContratosView, InicioView
from importacoes.views import (
    ImportacoesView,
    ImportarCronogramaView,
    ImportarElaboracaoView,
    ImportarIDView,
    ImportarSituacaoPadraoView,
    ImportarSituacaoPWView,
    BaixarModeloSituacaoPadraoView,
    LinhasRecusadasView,
    HistoricoImportacoesView,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("contratos/escolher/", HomeContratosView.as_view(), name="contratos_escolher"),
    path("contratos/ativar/", AtivarContratoView.as_view(), name="contrato_ativar"),
    path(
        "contas/login/",
        auth_views.LoginView.as_view(template_name="contas/login.html"),
        name="login",
    ),
    path(
        "contas/logout/",
        login_required(auth_views.LogoutView.as_view()),
        name="logout",
    ),
    path("importacoes/id/", ImportarIDView.as_view(), name="importar_id"),
    path("importacoes/", ImportacoesView.as_view(), name="importacoes_home"),
    path("importacoes/situacao-pw/", ImportarSituacaoPWView.as_view(), name="importar_situacao_pw"),
    path("importacoes/situacao-padrao/", ImportarSituacaoPadraoView.as_view(), name="importar_situacao_padrao"),
    path("importacoes/situacao-padrao/modelo/", BaixarModeloSituacaoPadraoView.as_view(), name="modelo_situacao_padrao"),
    path("importacoes/cronograma/", ImportarCronogramaView.as_view(), name="importar_cronograma"),
    path("importacoes/elaboracao/", ImportarElaboracaoView.as_view(), name="importar_elaboracao"),
    path("importacoes/recusadas/<int:contrato_id>/", LinhasRecusadasView.as_view(), name="linhas_recusadas"),
    path("importacoes/historico/<int:contrato_id>/", HistoricoImportacoesView.as_view(), name="historico_importacoes"),
    path("painel/", include("painel.urls")),
    path("contratos/", include("contratos.urls")),
    path("atividade/", include("registro.urls")),
    path("acoes/", include("acoes.urls")),
    path("documentos/", include("documentos.urls")),
    path("backups/", include("backups.urls")),
    path("grds/", include("grds.urls")),
    path("tarefas/", include("tarefas.urls")),
    path("", InicioView.as_view(), name="inicio"),
]
