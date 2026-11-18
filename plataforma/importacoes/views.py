from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from core.perfil import ErroPerfil, perfil_de_dict
from contratos.models import Contrato, PerfilContrato
from documentos.models import Documento

from .forms import ImportarIDForm
from .id_excel import (
    CATEGORIAS,
    ROTULOS_CATEGORIA,
    ErroFormatoID,
    LinhaPrevia,
    PreviaID,
    gerar_previa_id,
)
from .models import IndiceDocumentos
from .services import ErroAplicacaoID, aplicar_previa


CHAVE_SESSAO = "previa_importacao_id"
class ImportarIDView(LoginRequiredMixin, UserPassesTestMixin, View):
    template_name = "importacoes/id.html"
    raise_exception = True

    def test_func(self):
        return self.request.user.is_staff

    def get(self, request):
        request.session.pop(CHAVE_SESSAO, None)
        return render(
            request,
            self.template_name,
            {"form": ImportarIDForm(), "indices": IndiceDocumentos.objects.select_related("contrato")[:20]},
        )

    def post(self, request):
        if request.POST.get("acao") == "confirmar":
            return self._confirmar(request)
        return self._prever(request)

    def _prever(self, request):
        form = ImportarIDForm(request.POST, request.FILES)
        if not form.is_valid():
            return self._render_result(request, {"form": form})
        contrato = form.cleaned_data["contrato"]
        perfil_modelo = PerfilContrato.perfil_vigente(contrato, timezone.localdate())
        if perfil_modelo is None:
            form.add_error("contrato", "O contrato não tem perfil vigente para a data de hoje.")
            return self._render_result(request, {"form": form})
        try:
            perfil = perfil_de_dict(perfil_modelo.definicao)
            arquivo = form.cleaned_data["arquivo"]
            previa = gerar_previa_id(
                arquivo,
                nome_arquivo=arquivo.name,
                contrato_id=contrato.pk,
                perfil_id=perfil_modelo.pk,
                perfil=perfil,
                documentos_existentes=list(
                    Documento.objects.filter(contrato=contrato).values_list(
                        "identificador_base", "titulo"
                    )
                ),
                codigo_indice=form.cleaned_data["codigo_id"],
                revisao=form.cleaned_data["revisao"],
                data_importacao=timezone.localdate(),
            )
        except (ErroFormatoID, ErroPerfil, ValueError) as erro:
            return self._render_result(request, {"form": form, "erro": str(erro)})

        request.session[CHAVE_SESSAO] = {
            "usuario_id": request.user.pk,
            "contrato_id": previa.contrato_id,
            "perfil_id": previa.perfil_id,
            "fonte": previa.fonte,
            "codigo_indice": previa.codigo_indice,
            "revisao": previa.revisao,
            "arquivo_nome": previa.arquivo_nome,
            "formato": previa.formato,
            "linhas": [linha.__dict__ for linha in previa.linhas],
        }
        return self._render_result(
            request,
            {
                "form": form,
                "previa": previa,
                "contagens": [
                    (ROTULOS_CATEGORIA[categoria], previa.contagens[categoria])
                    for categoria in CATEGORIAS
                ],
                "indices": IndiceDocumentos.objects.select_related("contrato")[:20],
            },
        )

    def _render_result(self, request, context):
        template = self.template_name
        if request.headers.get("HX-Request") == "true":
            template = "importacoes/_resultado.html"
        return render(request, template, context)

    def _confirmar(self, request):
        dados = request.session.get(CHAVE_SESSAO)
        if not dados or dados.get("usuario_id") != request.user.pk:
            messages.error(request, "A prévia expirou. Envie o arquivo novamente.")
            return redirect("importar_id")
        try:
            previa = _previsao_da_sessao(dados)
            contrato = get_object_or_404(Contrato, pk=previa.contrato_id)
            perfil_modelo = get_object_or_404(
                PerfilContrato,
                pk=previa.perfil_id,
                contrato=contrato,
            )
            perfil_vigente = PerfilContrato.perfil_vigente(contrato, timezone.localdate())
            if perfil_vigente is None or perfil_vigente.pk != perfil_modelo.pk:
                raise ErroAplicacaoID("O perfil vigente mudou. Envie o arquivo e gere outra prévia.")
            indice = aplicar_previa(
                previa,
                contrato=contrato,
                perfil_modelo=perfil_modelo,
                usuario=request.user,
            )
        except (ErroAplicacaoID, ValueError, KeyError, TypeError) as erro:
            messages.error(request, str(erro))
            return redirect("importar_id")
        request.session.pop(CHAVE_SESSAO, None)
        messages.success(
            request,
            f"ID {indice.codigo}, revisão {indice.revisao}, importado com {indice.itens.count()} itens.",
        )
        return redirect("importar_id")


def _previsao_da_sessao(dados):
    return PreviaID(
        contrato_id=int(dados["contrato_id"]),
        perfil_id=int(dados["perfil_id"]),
        fonte=dados["fonte"],
        codigo_indice=dados["codigo_indice"],
        revisao=dados["revisao"],
        arquivo_nome=dados["arquivo_nome"],
        formato=dados["formato"],
        linhas=tuple(LinhaPrevia(**linha) for linha in dados["linhas"]),
    )
