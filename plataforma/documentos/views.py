from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import QueryDict
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from acoes.views import _contrato_da_requisicao

from .forms import (
    ColunaPersonalizadaForm,
    ColunasListaMestraForm,
    PreencherLoteColunaForm,
)
from .servicos import (
    DocumentosIndisponiveis,
    atualizar_motivo_reabertura,
    cancelar_documentos,
    carregar_confirmacao_cancelamento,
    carregar_confirmacao_reativacao,
    carregar_editor_colunas_lista_mestra,
    carregar_coluna_personalizada_lote,
    carregar_edicao_titulo,
    carregar_lista_documentos,
    carregar_lista_mestra,
    carregar_painel_documento,
    carregar_pasta_documento,
    editar_titulo_documento,
    criar_coluna_personalizada,
    desativar_coluna_personalizada,
    editar_coluna_personalizada,
    aplicar_preenchimento_lote_coluna,
    prever_preenchimento_lote_coluna,
    reativar_documentos,
    salvar_colunas_lista_mestra,
    salvar_valor_coluna_personalizada,
    voltar_colunas_lista_mestra_ao_padrao,
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


class ColunasListaMestraView(LoginRequiredMixin, View):
    template_name = "documentos/colunas_lista_mestra.html"

    def get(self, request):
        contrato_id = _contrato_da_requisicao(request)
        if contrato_id is None:
            return redirect("contratos_escolher")
        contexto = carregar_editor_colunas_lista_mestra(request.user, contrato_id)
        contexto["form"] = self._formulario(contexto)
        self._preparar_formularios_personalizados(contexto)
        contexto["url_lista"] = _url_lista_mestra(contexto["contrato"].pk)
        return render(request, self.template_name, contexto)

    def post(self, request):
        contrato_id = _contrato_da_requisicao(request, incluir_post=True)
        if contrato_id is None:
            return redirect("contratos_escolher")
        contexto = carregar_editor_colunas_lista_mestra(request.user, contrato_id)
        acao = request.POST.get("acao")
        if acao == "criar_coluna":
            form_coluna = ColunaPersonalizadaForm(data=request.POST)
            if form_coluna.is_valid():
                try:
                    criar_coluna_personalizada(
                        request.user,
                        contrato_id,
                        **form_coluna.cleaned_data,
                    )
                except (ValueError, ValidationError) as erro:
                    form_coluna.add_error(None, str(erro))
                else:
                    messages.success(request, "Coluna do contrato criada.")
                    return redirect(_url_colunas_lista_mestra(contexto["contrato"].pk))
            contexto["form"] = self._formulario(contexto)
            self._preparar_formularios_personalizados(contexto, form_criacao=form_coluna)
            contexto["url_lista"] = _url_lista_mestra(contexto["contrato"].pk)
            return render(request, self.template_name, contexto, status=400)

        if acao == "editar_coluna":
            coluna = next(
                (
                    item
                    for item in contexto["colunas_personalizadas"]
                    if item.pk == _int_ou_none(request.POST.get("coluna_id")) and item.ativa
                ),
                None,
            )
            if coluna is None:
                raise PermissionDenied("A coluna selecionada não está disponível.")
            form_edicao = ColunaPersonalizadaForm(instance=coluna, data=request.POST)
            if form_edicao.is_valid():
                try:
                    editar_coluna_personalizada(
                        request.user,
                        contrato_id,
                        coluna.pk,
                        **form_edicao.cleaned_data,
                    )
                except (ValueError, ValidationError) as erro:
                    form_edicao.add_error(None, str(erro))
                else:
                    messages.success(request, "Coluna do contrato atualizada.")
                    return redirect(_url_colunas_lista_mestra(contexto["contrato"].pk))
            contexto["form"] = self._formulario(contexto)
            self._preparar_formularios_personalizados(
                contexto,
                formularios_edicao={coluna.pk: form_edicao},
            )
            contexto["url_lista"] = _url_lista_mestra(contexto["contrato"].pk)
            return render(request, self.template_name, contexto, status=400)

        if acao == "desativar_coluna":
            desativar_coluna_personalizada(
                request.user,
                contrato_id,
                request.POST.get("coluna_id"),
            )
            messages.success(request, "Coluna desativada. Os valores foram preservados.")
            return redirect(_url_colunas_lista_mestra(contexto["contrato"].pk))

        if acao == "padrao":
            voltar_colunas_lista_mestra_ao_padrao(request.user, contrato_id)
            messages.success(request, "As colunas voltaram ao padrão da Lista Mestra.")
            return redirect(_url_lista_mestra(contexto["contrato"].pk))

        form = ColunasListaMestraForm(
            colunas=contexto["colunas_editor"],
            selecionadas=[
                chave for chave in contexto["chaves_visiveis"] if chave != "codigo"
            ],
            ordem=contexto["ordem_editor"],
            data=request.POST,
        )
        if form.is_valid():
            salvar_colunas_lista_mestra(
                request.user,
                contrato_id,
                form.cleaned_data["visiveis"],
                form.cleaned_data["ordem"],
            )
            messages.success(request, "Colunas da Lista Mestra salvas.")
            return redirect(_url_lista_mestra(contexto["contrato"].pk))

        contexto["form"] = form
        self._preparar_formularios_personalizados(contexto)
        contexto["url_lista"] = _url_lista_mestra(contexto["contrato"].pk)
        return render(request, self.template_name, contexto, status=400)

    @staticmethod
    def _preparar_formularios_personalizados(
        contexto,
        *,
        form_criacao=None,
        formularios_edicao=None,
    ):
        contexto["form_coluna_personalizada"] = form_criacao or ColunaPersonalizadaForm()
        formularios_edicao = formularios_edicao or {}
        for coluna in contexto["colunas_personalizadas"]:
            coluna.form_edicao = formularios_edicao.get(
                coluna.pk,
                ColunaPersonalizadaForm(instance=coluna) if coluna.ativa else None,
            )

    @staticmethod
    def _formulario(contexto, data=None):
        return ColunasListaMestraForm(
            colunas=contexto["colunas_editor"],
            selecionadas=[
                chave for chave in contexto["chaves_visiveis"] if chave != "codigo"
            ],
            ordem=contexto["ordem_editor"],
            data=data,
        )


class PreencherLoteColunaView(LoginRequiredMixin, View):
    template_name = "documentos/preencher_lote_coluna.html"

    def get(self, request, coluna_id):
        contrato_id = _contrato_da_requisicao(request)
        if contrato_id is None:
            return redirect("contratos_escolher")
        contexto = carregar_coluna_personalizada_lote(request.user, contrato_id, coluna_id)
        contexto["form"] = PreencherLoteColunaForm(coluna=contexto["coluna"])
        contexto["url_colunas"] = _url_colunas_lista_mestra(contexto["contrato"].pk)
        return render(request, self.template_name, contexto)

    def post(self, request, coluna_id):
        contrato_id = _contrato_da_requisicao(request, incluir_post=True)
        if contrato_id is None:
            return redirect("contratos_escolher")
        contexto = carregar_coluna_personalizada_lote(request.user, contrato_id, coluna_id)
        form = PreencherLoteColunaForm(coluna=contexto["coluna"], data=request.POST)
        previa = None
        erro = ""
        if form.is_valid():
            dados = form.cleaned_data
            try:
                if request.POST.get("acao") == "aplicar":
                    resultado = aplicar_preenchimento_lote_coluna(
                        request.user,
                        contrato_id,
                        coluna_id,
                        codigos=dados["codigos"],
                        valor=dados["valor"],
                        motivo=dados["motivo"],
                        substituir=dados["substituir"],
                        revisao=dados.get("revisao", ""),
                    )
                    messages.success(
                        request,
                        f'{resultado["aplicados"]} valor(es) atualizado(s); '
                        f'{resultado["sem_alteracao"]} sem alteração; '
                        f'{resultado["conflitos_ignorados"]} conflito(s) preservado(s).',
                    )
                    return redirect(_url_coluna_lote(contexto["contrato"].pk, coluna_id))
                previa = prever_preenchimento_lote_coluna(
                    request.user,
                    contrato_id,
                    coluna_id,
                    codigos=dados["codigos"],
                    valor=dados["valor"],
                    revisao=dados.get("revisao", ""),
                )
            except (ValueError, ValidationError) as excecao:
                erro = str(excecao)
        contexto.update(
            {
                "form": form,
                "previa": previa,
                "erro": erro,
                "url_colunas": _url_colunas_lista_mestra(contexto["contrato"].pk),
            }
        )
        return render(request, self.template_name, contexto, status=400 if erro or not form.is_valid() else 200)

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
        if request.POST.get("acao") == "valor_coluna_personalizada":
            try:
                _, mudou = salvar_valor_coluna_personalizada(
                    request.user,
                    contrato_id,
                    documento_id,
                    request.POST.get("coluna_id"),
                    valor=request.POST.get("valor", ""),
                    motivo=request.POST.get("motivo", ""),
                    emissao_id=request.POST.get("emissao_id") or None,
                )
            except PermissionDenied:
                raise
            except (TypeError, ValueError, ValidationError) as erro:
                messages.error(request, str(erro))
            else:
                if mudou:
                    messages.success(request, "Campo do contrato atualizado.")
                else:
                    messages.info(request, "O campo já tinha esse valor; nenhuma alteração foi registrada.")
            return redirect("documento_pasta", contrato_id=contrato_id, documento_id=documento_id)

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


class DocumentoPainelView(LoginRequiredMixin, View):
    template_name = "documentos/_painel_lateral.html"

    def get(self, request, contrato_id, documento_id):
        contexto = carregar_painel_documento(request.user, contrato_id, documento_id)
        return render(request, self.template_name, contexto)


class EditarTituloDocumentoView(LoginRequiredMixin, View):
    template_name = "documentos/editar_titulo.html"

    def get(self, request, contrato_id, documento_id):
        contexto = carregar_edicao_titulo(request.user, contrato_id, documento_id)
        return render(request, self.template_name, contexto)

    def post(self, request, contrato_id, documento_id):
        try:
            editar_titulo_documento(
                request.user,
                contrato_id,
                documento_id,
                request.POST.get("titulo", ""),
                request.POST.get("motivo", ""),
            )
        except PermissionDenied:
            raise
        except ValueError as erro:
            contexto = carregar_edicao_titulo(request.user, contrato_id, documento_id)
            contexto.update(
                {
                    "titulo_informado": request.POST.get("titulo", ""),
                    "motivo_informado": request.POST.get("motivo", ""),
                    "erro": str(erro),
                }
            )
            return render(request, self.template_name, contexto, status=400)

        messages.success(request, "Título atualizado.")
        return redirect(
            "documento_pasta",
            contrato_id=contrato_id,
            documento_id=documento_id,
        )


def _url_lista(contrato_id, consulta):
    parametros = QueryDict(consulta or "", mutable=True)
    parametros["contrato"] = str(contrato_id)
    return f"{reverse('documentos_lista')}?{parametros.urlencode()}"


def _url_lista_mestra(contrato_id):
    return f"{reverse('lista_mestra')}?contrato={contrato_id}"


def _url_colunas_lista_mestra(contrato_id):
    return f"{reverse('lista_mestra_colunas')}?contrato={contrato_id}"


def _url_coluna_lote(contrato_id, coluna_id):
    return f"{reverse('lista_mestra_coluna_lote', args=(coluna_id,))}?contrato={contrato_id}"


def _int_ou_none(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None
