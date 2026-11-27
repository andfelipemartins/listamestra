from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import QueryDict
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from .servicos import (
    DocumentosIndisponiveis,
    atualizar_motivo_reabertura,
    cancelar_documentos,
    carregar_confirmacao_cancelamento,
    carregar_confirmacao_reativacao,
    carregar_lista_documentos,
    carregar_lista_mestra,
    carregar_pasta_documento,
    reativar_documentos,
)


class DocumentosListaView(LoginRequiredMixin, View):
    template_name = "documentos/lista.html"

    def get(self, request):
        filtros_caixas = {
            chave.removeprefix("caixa_"): request.GET.getlist(chave)
            for chave in request.GET
            if chave.startswith("caixa_")
        }
        try:
            contexto = carregar_lista_documentos(
                request.user,
                request.GET.get("contrato"),
                busca=request.GET.get("q", ""),
                filtros_caixas=filtros_caixas,
                categoria=request.GET.get("categoria", ""),
                situacao=request.GET.get("situacao", ""),
                pagina=request.GET.get("pagina", 1),
            )
        except DocumentosIndisponiveis as erro:
            contexto = {
                "contratos": [],
                "contrato": None,
                "erro": str(erro),
            }
        query_sem_pagina = request.GET.copy()
        query_sem_pagina.pop("pagina", None)
        contexto["query_sem_pagina"] = query_sem_pagina.urlencode()
        return render(request, self.template_name, contexto)


class ListaMestraView(LoginRequiredMixin, View):
    template_name = "documentos/lista_mestra.html"

    def get(self, request):
        try:
            contexto = carregar_lista_mestra(
                request.user,
                request.GET.get("contrato"),
                busca=request.GET.get("q", ""),
                tipo=request.GET.get("tipo", ""),
                disciplina=request.GET.get("disciplina", ""),
                fase=request.GET.get("fase", ""),
                situacao=request.GET.get("situacao", ""),
                mostrar_cancelados=request.GET.get("mostrar_cancelados") == "1",
                pagina=request.GET.get("pagina", 1),
            )
        except DocumentosIndisponiveis as erro:
            contexto = {
                "contratos": [],
                "contrato": None,
                "erro": str(erro),
            }
        query_sem_pagina = request.GET.copy()
        query_sem_pagina.pop("pagina", None)
        contexto["query_sem_pagina"] = query_sem_pagina.urlencode()
        return render(request, self.template_name, contexto)


class CancelarDocumentosView(LoginRequiredMixin, View):
    template_name = "documentos/lista.html"

    def get(self, request, contrato_id):
        try:
            contexto = carregar_confirmacao_cancelamento(
                request.user,
                contrato_id,
                request.GET.getlist("documento"),
            )
        except PermissionDenied:
            raise
        except (DocumentosIndisponiveis, ValueError) as erro:
            messages.error(request, str(erro))
            return redirect(_url_lista(contrato_id, request.GET.get("lista_query", "")))
        return self._render_confirmacao(request, contexto, request.GET)

    def post(self, request, contrato_id):
        ids = request.POST.getlist("documento")
        try:
            contexto = carregar_confirmacao_cancelamento(request.user, contrato_id, ids)
        except PermissionDenied:
            raise
        except (DocumentosIndisponiveis, ValueError) as erro:
            messages.error(request, str(erro))
            return redirect(_url_lista(contrato_id, request.POST.get("lista_query", "")))

        try:
            resultado = cancelar_documentos(
                request.user,
                contexto["contrato"],
                ids,
                request.POST.get("motivo_cancelamento", ""),
                request.POST.get("motivo_cancelamento_obs", ""),
            )
        except PermissionDenied:
            raise
        except (DocumentosIndisponiveis, ValueError) as erro:
            contexto["erro_cancelamento"] = str(erro)
            return self._render_confirmacao(request, contexto, request.POST, status=400)

        if resultado["quantidade_cancelada"]:
            messages.success(
                request,
                f'{resultado["quantidade_cancelada"]} documento(s) cancelado(s).',
            )
        else:
            messages.info(request, "Nenhum documento novo foi cancelado.")
        if resultado["ignorados"]:
            avisos = "; ".join(
                f'{item["codigo"]}: {item["motivo"]}' for item in resultado["ignorados"]
            )
            messages.warning(request, f"Documentos ignorados: {avisos}.")
        return redirect(_url_lista(contrato_id, request.POST.get("lista_query", "")))

    def _render_confirmacao(self, request, contexto, dados, *, status=200):
        contexto.update(
            {
                "confirmar_cancelamento": True,
                "lista_query": dados.get("lista_query", ""),
                "motivo_cancelamento_selecionado": dados.get("motivo_cancelamento", ""),
                "observacao_cancelamento": dados.get("motivo_cancelamento_obs", ""),
                "url_lista": _url_lista(contexto["contrato"].pk, dados.get("lista_query", "")),
            }
        )
        return render(request, self.template_name, contexto, status=status)


class ReativarDocumentosView(LoginRequiredMixin, View):
    template_name = "documentos/lista.html"

    def get(self, request, contrato_id):
        try:
            contexto = carregar_confirmacao_reativacao(
                request.user,
                contrato_id,
                request.GET.getlist("documento"),
            )
        except PermissionDenied:
            raise
        except (DocumentosIndisponiveis, ValueError) as erro:
            messages.error(request, str(erro))
            return redirect(_url_lista(contrato_id, request.GET.get("lista_query", "")))
        return self._render_confirmacao(request, contexto, request.GET)

    def post(self, request, contrato_id):
        ids = request.POST.getlist("documento")
        try:
            contexto = carregar_confirmacao_reativacao(request.user, contrato_id, ids)
        except PermissionDenied:
            raise
        except (DocumentosIndisponiveis, ValueError) as erro:
            messages.error(request, str(erro))
            return redirect(_url_lista(contrato_id, request.POST.get("lista_query", "")))

        try:
            resultado = reativar_documentos(
                request.user,
                contexto["contrato"],
                ids,
                request.POST.get("observacao_reativacao", ""),
            )
        except PermissionDenied:
            raise
        except (DocumentosIndisponiveis, ValueError) as erro:
            contexto["erro_reativacao"] = str(erro)
            return self._render_confirmacao(request, contexto, request.POST, status=400)

        if resultado["quantidade_reativada"]:
            messages.success(
                request,
                f'{resultado["quantidade_reativada"]} documento(s) reativado(s).',
            )
        else:
            messages.info(request, "Nenhum documento foi reativado.")
        if resultado["ignorados"]:
            avisos = "; ".join(
                f'{item["codigo"]}: {item["motivo"]}' for item in resultado["ignorados"]
            )
            messages.warning(request, f"Documentos ignorados: {avisos}.")
        return redirect(_url_lista(contrato_id, request.POST.get("lista_query", "")))

    def _render_confirmacao(self, request, contexto, dados, *, status=200):
        contexto.update(
            {
                "confirmar_reativacao": True,
                "lista_query": dados.get("lista_query", ""),
                "observacao_reativacao": dados.get("observacao_reativacao", ""),
                "url_lista": _url_lista(contexto["contrato"].pk, dados.get("lista_query", "")),
            }
        )
        return render(request, self.template_name, contexto, status=status)


class DocumentoPastaView(LoginRequiredMixin, View):
    template_name = "documentos/pasta.html"

    def get(self, request, contrato_id, documento_id):
        try:
            contexto = carregar_pasta_documento(request.user, contrato_id, documento_id)
        except DocumentosIndisponiveis as erro:
            contexto = {"erro": str(erro), "contrato_id": contrato_id}
        return render(request, self.template_name, contexto)

    def post(self, request, contrato_id, documento_id):
        try:
            atualizar_motivo_reabertura(
                request.user,
                contrato_id,
                documento_id,
                request.POST.get("emissao"),
                request.POST.get("motivo_reabertura", ""),
                request.POST.get("motivo_reabertura_obs", ""),
            )
        except PermissionDenied:
            raise
        except (TypeError, ValueError) as erro:
            messages.error(request, str(erro))
        else:
            messages.success(request, "Motivo da reabertura atualizado.")
        return redirect("documento_pasta", contrato_id=contrato_id, documento_id=documento_id)


def _url_lista(contrato_id, consulta):
    parametros = QueryDict(consulta or "", mutable=True)
    parametros["contrato"] = str(contrato_id)
    return f"{reverse('documentos_lista')}?{parametros.urlencode()}"
