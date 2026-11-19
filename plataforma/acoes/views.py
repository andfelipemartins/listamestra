from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from .services import (
    carregar_ignorados,
    carregar_janela,
    reativar_ignorado,
    registrar_acao,
)


class JanelaView(LoginRequiredMixin, View):
    template_name = "acoes/janela.html"

    def get(self, request, tipo):
        try:
            contexto = carregar_janela(request.user, request.GET.get("contrato"), tipo)
        except ValueError as erro:
            from django.http import Http404

            raise Http404 from erro
        contexto["email_aberto"] = request.GET.get("email", "")
        return render(request, self.template_name, contexto)


class IgnoradosView(LoginRequiredMixin, View):
    template_name = "acoes/ignorados.html"

    def get(self, request):
        contexto = carregar_ignorados(request.user, request.GET.get("contrato"))
        return render(request, self.template_name, contexto)


class AcaoView(LoginRequiredMixin, View):
    def post(self, request):
        tipo_janela = "erros"
        contrato_id = request.POST.get("contrato")
        try:
            acao = registrar_acao(
                request.user,
                contrato_id,
                request.POST.get("documento"),
                request.POST.get("tipo_pendencia", ""),
                request.POST.get("acao", ""),
                request.POST.get("motivo", ""),
            )
        except PermissionDenied:
            raise
        except (TypeError, ValueError) as erro:
            messages.error(request, str(erro))
        else:
            if acao.acao == "pedir_correcao":
                messages.success(request, "Pedido registrado. O texto do e-mail está pronto para copiar.")
                return redirect(
                    f"{reverse('acoes:janela', args=(tipo_janela,))}?contrato={contrato_id}&email={acao.pk}"
                )
            if acao.acao == "ignorar":
                messages.success(request, "Pendência ignorada. Você pode reativá-la em ‘ver todos > ignorados’.")
            else:
                messages.success(request, "Correção registrada. O item continuará aqui até outra situação chegar por importação.")
        return redirect(f"{reverse('acoes:janela', args=(tipo_janela,))}?contrato={contrato_id}")


class ReativarView(LoginRequiredMixin, View):
    def post(self, request):
        contrato_id = request.POST.get("contrato")
        try:
            reativar_ignorado(
                request.user,
                contrato_id,
                request.POST.get("documento"),
                request.POST.get("tipo_pendencia", ""),
            )
        except PermissionDenied:
            raise
        except (TypeError, ValueError) as erro:
            messages.error(request, str(erro))
        else:
            messages.success(request, "Pendência reativada na janela de erros.")
        return redirect(f"{reverse('acoes:ignorados')}?contrato={contrato_id}")
