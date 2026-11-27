from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from acoes.services import contratos_acessiveis, resolver_contrato
from documentos.servicos import DocumentosIndisponiveis

from .forms import GrdForm
from .models import Grd
from .servicos import (
    criar_grd,
    listar_grds,
    pode_criar_grd,
    preparar_grd,
)


class ListaGrdsView(LoginRequiredMixin, View):
    template_name = "grds/lista.html"

    def get(self, request):
        contratos = list(contratos_acessiveis(request.user))
        if not contratos:
            raise PermissionDenied
        contrato = resolver_contrato(request.user, request.GET.get("contrato"))
        return render(
            request,
            self.template_name,
            {
                "contratos": contratos,
                "contrato": contrato,
                "grds": listar_grds(contrato),
                "pode_criar": pode_criar_grd(request.user, contrato),
            },
        )


class NovaGrdView(LoginRequiredMixin, View):
    template_name = "grds/nova.html"

    def get(self, request):
        contratos = contratos_acessiveis(request.user)
        contrato = resolver_contrato(request.user, request.GET.get("contrato"))
        if contrato is None:
            raise PermissionDenied
        if not pode_criar_grd(request.user, contrato):
            raise PermissionDenied
        form = GrdForm(
            contratos=contratos,
            initial={"contrato": contrato.pk, "data": timezone.localdate()},
        )
        return render(request, self.template_name, {"form": form, "contrato": contrato})

    def post(self, request):
        contratos = contratos_acessiveis(request.user)
        contrato_id = request.POST.get("contrato")
        contrato = resolver_contrato(request.user, contrato_id)
        if contrato is None or not pode_criar_grd(request.user, contrato):
            raise PermissionDenied

        form = GrdForm(request.POST, contratos=contratos)
        etapa = request.POST.get("etapa", "previa")
        previa = None
        erro = ""
        if form.is_valid():
            dados = form.cleaned_data
            if etapa == "confirmar":
                try:
                    resultado = criar_grd(
                        dados["contrato"],
                        request.user,
                        dados["data"],
                        dados["destinatario"],
                        dados["observacao"],
                        dados["texto_codigos"],
                    )
                except DocumentosIndisponiveis as excecao:
                    erro = str(excecao)
                else:
                    if resultado["grd"] is None:
                        previa = resultado
                        erro = resultado["erro"]
                    else:
                        messages.success(request, f"{resultado['grd'].rotulo()} criada.")
                        return redirect(
                            "grds:detalhe",
                            contrato_id=contrato.pk,
                            grd_id=resultado["grd"].pk,
                        )
            elif etapa == "editar":
                pass
            else:
                try:
                    previa = preparar_grd(dados["contrato"], dados["texto_codigos"])
                except DocumentosIndisponiveis as excecao:
                    erro = str(excecao)

        return render(
            request,
            self.template_name,
            {
                "form": form,
                "contrato": contrato,
                "previa": previa,
                "erro": erro,
                "etapa": etapa,
            },
            status=400 if form.errors else 200,
        )


class DetalheGrdView(LoginRequiredMixin, View):
    template_name = "grds/detalhe.html"

    def get(self, request, contrato_id, grd_id):
        contrato = resolver_contrato(request.user, contrato_id)
        grd = get_object_or_404(
            Grd.objects.filter(contrato=contrato)
            .select_related("contrato", "criado_por")
            .prefetch_related("itens__emissao__documento"),
            pk=grd_id,
        )
        return render(
            request,
            self.template_name,
            {
                "contrato": contrato,
                "grd": grd,
                "itens": grd.itens.all(),
                "url_lista": f"{reverse('grds:lista')}?contrato={contrato.pk}",
            },
        )
