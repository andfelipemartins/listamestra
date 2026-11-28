from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from .services import contratos_para_selecao, resolver_contrato
from .services import (
    JANELA_TITULO_DIFERENTE_ID,
    PENDENCIA_TITULO_DIFERENTE_ID,
    carregar_ignorados,
    carregar_abertas,
    carregar_atrasados,
    carregar_atrasados_lado,
    carregar_janela,
    carregar_minha_mesa,
    carregar_resumo_inicio,
    reativar_ignorado,
    registrar_acao,
)


def _contrato_da_requisicao(request, *, incluir_post=False):
    contrato_id = request.GET.get("contrato")
    if not contrato_id and incluir_post:
        contrato_id = request.POST.get("contrato")

    if contrato_id:
        contrato = resolver_contrato(request.user, contrato_id)
        if not contrato.ativo and not request.user.is_staff:
            raise PermissionDenied("Este contrato est\u00e1 inativo.")
        request.session["contrato_ativo_id"] = contrato.pk
        return contrato.pk

    contrato_id = request.session.get("contrato_ativo_id")
    if not contrato_id:
        return None
    try:
        contrato = resolver_contrato(request.user, contrato_id)
    except PermissionDenied:
        request.session.pop("contrato_ativo_id", None)
        return None
    if not contrato.ativo:
        request.session.pop("contrato_ativo_id", None)
        return None
    return contrato.pk


def _sem_contrato():
    return redirect("contratos_escolher")


class InicioView(LoginRequiredMixin, View):
    template_name = "inicio.html"

    def get(self, request):
        contrato_id = _contrato_da_requisicao(request)
        if contrato_id is None:
            return _sem_contrato()
        contexto = carregar_resumo_inicio(request.user, contrato_id)
        return render(request, self.template_name, contexto)


class HomeContratosView(LoginRequiredMixin, View):
    template_name = "contratos_escolher.html"

    def get(self, request):
        contratos = contratos_para_selecao(request.user)
        ids_disponiveis = {item["contrato"].pk for item in contratos}
        if request.session.get("contrato_ativo_id") not in ids_disponiveis:
            request.session.pop("contrato_ativo_id", None)
        if len(contratos) == 1:
            request.session["contrato_ativo_id"] = contratos[0]["contrato"].pk
            return redirect("inicio")
        return render(
            request,
            self.template_name,
            {
                "contratos_disponiveis": contratos,
                "modo_contratos": request.session.get("modo_contratos", "grade"),
            },
        )

    def post(self, request):
        modo = request.POST.get("modo")
        if modo in {"grade", "lista"}:
            request.session["modo_contratos"] = modo
        return redirect("contratos_escolher")


class AtivarContratoView(LoginRequiredMixin, View):
    def post(self, request):
        contrato_id = request.POST.get("contrato")
        if not contrato_id:
            raise PermissionDenied("Informe um contrato para ativar.")
        contrato = resolver_contrato(request.user, contrato_id)
        if not contrato.ativo:
            raise PermissionDenied("Este contrato est\u00e1 inativo.")
        request.session["contrato_ativo_id"] = contrato.pk
        return redirect("inicio")


class PendenciasView(LoginRequiredMixin, View):
    template_name = "acoes/pendencias.html"

    def get(self, request):
        contrato_id = _contrato_da_requisicao(request)
        if contrato_id is None:
            return _sem_contrato()
        contexto = carregar_minha_mesa(request.user, contrato_id)
        contexto["email_aberto"] = request.GET.get("email", "")
        return render(request, self.template_name, contexto)


class AtrasadosView(LoginRequiredMixin, View):
    template_name = "acoes/atrasados.html"

    def get(self, request):
        contrato_id = _contrato_da_requisicao(request)
        if contrato_id is None:
            return _sem_contrato()
        contexto = carregar_atrasados(request.user, contrato_id)
        return render(request, self.template_name, contexto)


class AbertasView(LoginRequiredMixin, View):
    template_name = "acoes/abertas.html"

    def get(self, request):
        contrato_id = _contrato_da_requisicao(request)
        if contrato_id is None:
            return _sem_contrato()
        contexto = carregar_abertas(request.user, contrato_id)
        return render(request, self.template_name, contexto)


class AtrasadosLadoView(LoginRequiredMixin, View):
    template_name = "acoes/atrasados_lado.html"

    def get(self, request, lado):
        contrato_id = _contrato_da_requisicao(request)
        if contrato_id is None:
            return _sem_contrato()
        try:
            contexto = carregar_atrasados_lado(request.user, contrato_id, lado)
        except ValueError as erro:
            from django.http import Http404

            raise Http404 from erro
        return render(request, self.template_name, contexto)


class AtrasadosLegadoView(LoginRequiredMixin, View):
    def get(self, request):
        contrato_id = _contrato_da_requisicao(request)
        if contrato_id is None:
            return _sem_contrato()
        destino = reverse("acoes:atrasados")
        destino = f"{destino}?contrato={contrato_id}"
        return redirect(destino)


class JanelaView(LoginRequiredMixin, View):
    template_name = "acoes/janela.html"

    def get(self, request, tipo):
        contrato_id = _contrato_da_requisicao(request)
        if contrato_id is None:
            return _sem_contrato()
        try:
            contexto = carregar_janela(request.user, contrato_id, tipo)
        except ValueError as erro:
            from django.http import Http404

            raise Http404 from erro
        contexto["email_aberto"] = request.GET.get("email", "")
        return render(request, self.template_name, contexto)


class IgnoradosView(LoginRequiredMixin, View):
    template_name = "acoes/ignorados.html"

    def get(self, request):
        contrato_id = _contrato_da_requisicao(request)
        if contrato_id is None:
            return _sem_contrato()
        contexto = carregar_ignorados(request.user, contrato_id)
        return render(request, self.template_name, contexto)


class AcaoView(LoginRequiredMixin, View):
    def post(self, request):
        contrato_id = _contrato_da_requisicao(request, incluir_post=True)
        if contrato_id is None:
            return _sem_contrato()
        tipo_pendencia = request.POST.get("tipo_pendencia", "")
        tipo_janela = (
            JANELA_TITULO_DIFERENTE_ID
            if tipo_pendencia == PENDENCIA_TITULO_DIFERENTE_ID
            else "erros"
        )
        try:
            acao = registrar_acao(
                request.user,
                contrato_id,
                request.POST.get("documento"),
                tipo_pendencia,
                request.POST.get("acao", ""),
                request.POST.get("motivo", ""),
            )
        except PermissionDenied:
            raise
        except (TypeError, ValueError) as erro:
            messages.error(request, str(erro))
        else:
            if acao.acao == "pedir_correcao" and acao.tipo_pendencia == "falta_no_pw":
                messages.success(request, "Pedido de inclusão registrado.")
                return redirect(f"{reverse('acoes:pendencias')}?contrato={contrato_id}")
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


class UsarTituloIDView(LoginRequiredMixin, View):
    def post(self, request):
        contrato_id = _contrato_da_requisicao(request, incluir_post=True)
        if contrato_id is None:
            return _sem_contrato()
        try:
            contexto = carregar_janela(
                request.user,
                contrato_id,
                JANELA_TITULO_DIFERENTE_ID,
            )
            documento_id = int(request.POST.get("documento"))
            pendencia = next(
                (
                    item for item in contexto["janela"]["todos"]
                    if item["documento"].pk == documento_id
                    and item["tipo_pendencia"] == PENDENCIA_TITULO_DIFERENTE_ID
                ),
                None,
            )
            if pendencia is None:
                raise ValueError("A pendência já não está aberta para ação.")

            from documentos.servicos import editar_titulo_documento

            editar_titulo_documento(
                request.user,
                contrato_id,
                documento_id,
                pendencia["titulo_id"],
                f"Conciliação com o ID {pendencia['codigo_id']}",
            )
        except PermissionDenied:
            raise
        except (TypeError, ValueError) as erro:
            messages.error(request, str(erro))
        else:
            messages.success(request, "Título atualizado conforme o ID.")
        return redirect(
            f"{reverse('acoes:janela', args=(JANELA_TITULO_DIFERENTE_ID,))}"
            f"?contrato={contrato_id}"
        )


class ReativarView(LoginRequiredMixin, View):
    def post(self, request):
        contrato_id = _contrato_da_requisicao(request, incluir_post=True)
        if contrato_id is None:
            return _sem_contrato()
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
