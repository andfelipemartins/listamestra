from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.views import View

from .servicos import (
    DocumentosIndisponiveis,
    carregar_lista_documentos,
    carregar_pasta_documento,
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


class DocumentoPastaView(LoginRequiredMixin, View):
    template_name = "documentos/pasta.html"

    def get(self, request, contrato_id, documento_id):
        try:
            contexto = carregar_pasta_documento(request.user, contrato_id, documento_id)
        except DocumentosIndisponiveis as erro:
            contexto = {"erro": str(erro), "contrato_id": contrato_id}
        return render(request, self.template_name, contexto)
