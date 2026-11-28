import base64
import mimetypes

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from acoes.services import contratos_acessiveis, resolver_contrato
from documentos.servicos import DocumentosIndisponiveis

from .forms import GrdCampoCabecalhoFormSet, GrdConfiguracaoForm, GrdForm
from .models import Grd, GrdCampoCabecalho
from .servicos import (
    criar_grd,
    dados_cabecalho_previa,
    garantir_configuracao_grd,
    listar_grds,
    pode_configurar_grd,
    pode_criar_grd,
    preparar_grd,
)


def _contrato_ativo(request):
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
    return contrato


def _contratos_escolher():
    return redirect("contratos_escolher")


def _logo_data_uri(configuracao):
    if not configuracao.logo:
        return ""
    tipo, _ = mimetypes.guess_type(configuracao.logo.name)
    with configuracao.logo.open("rb") as arquivo:
        conteudo = base64.b64encode(arquivo.read()).decode("ascii")
    return f"data:{tipo or 'image/png'};base64,{conteudo}"


def _valores_digitados(form, configuracao):
    return {
        str(campo.pk): form.cleaned_data.get(f"campo_{campo.pk}", "").strip()
        for campo in configuracao.campos.filter(
            habilitado=True, fonte=GrdCampoCabecalho.Fonte.DIGITADO
        )
    }


def _copias_post(request, previa, formatos, *, validar=False):
    copias = {}
    erros = []
    for item in previa["aceitos"]:
        emissao_id = item["emissao"].pk
        quantidades = {}
        for formato in formatos:
            campo = f"qtd_{emissao_id}_{formato}"
            bruto = request.POST.get(campo)
            padrao = 1 if formato == "Digital" else 0
            try:
                quantidade = padrao if bruto in (None, "") else int(bruto)
                if quantidade < 0 or quantidade > 999:
                    raise ValueError
            except (TypeError, ValueError):
                erros.append(f"Informe uma quantidade entre 0 e 999 para {formato}.")
                quantidade = padrao
            quantidades[formato] = quantidade
        copias[emissao_id] = quantidades
    if validar and erros:
        return copias, erros[0]
    return copias, ""


def _enriquecer_previa(previa, cabecalho, copias):
    previa["cabecalho"] = cabecalho["campos"]
    previa["numero_formatado"] = cabecalho["numero_formatado"]
    previa["formatos_copias"] = cabecalho["formatos_copias"]
    for item in previa["aceitos"]:
        valores = copias.get(item["emissao"].pk, {})
        item["copias_form"] = [
            {
                "nome": f"qtd_{item['emissao'].pk}_{formato}",
                "formato": formato,
                "valor": valores.get(formato, 1 if formato == "Digital" else 0),
            }
            for formato in cabecalho["formatos_copias"]
        ]


class ListaGrdsView(LoginRequiredMixin, View):
    template_name = "grds/lista.html"

    def get(self, request):
        contratos = list(contratos_acessiveis(request.user))
        if not contratos:
            raise PermissionDenied
        contrato_id = request.GET.get("contrato") or request.session.get("contrato_ativo_id")
        contrato = resolver_contrato(request.user, contrato_id)
        if contrato:
            request.session["contrato_ativo_id"] = contrato.pk
            garantir_configuracao_grd(contrato)
        return render(
            request,
            self.template_name,
            {
                "contratos": contratos,
                "contrato": contrato,
                "grds": listar_grds(contrato),
                "pode_criar": pode_criar_grd(request.user, contrato),
                "pode_configurar": pode_configurar_grd(request.user, contrato),
            },
        )


class NovaGrdView(LoginRequiredMixin, View):
    template_name = "grds/nova.html"

    def get(self, request):
        contratos = contratos_acessiveis(request.user)
        contrato_id = request.GET.get("contrato") or request.session.get("contrato_ativo_id")
        contrato = resolver_contrato(request.user, contrato_id)
        if contrato is None:
            raise PermissionDenied
        request.session["contrato_ativo_id"] = contrato.pk
        if not pode_criar_grd(request.user, contrato):
            raise PermissionDenied
        configuracao = garantir_configuracao_grd(contrato)
        form = GrdForm(
            contratos=contratos,
            configuracao=configuracao,
            initial={"contrato": contrato.pk, "data": timezone.localdate()},
        )
        return render(
            request,
            self.template_name,
            {"form": form, "contrato": contrato, "configuracao": configuracao},
        )

    def post(self, request):
        contratos = contratos_acessiveis(request.user)
        contrato_id = request.POST.get("contrato")
        contrato = resolver_contrato(request.user, contrato_id)
        if contrato is None or not pode_criar_grd(request.user, contrato):
            raise PermissionDenied
        request.session["contrato_ativo_id"] = contrato.pk
        configuracao = garantir_configuracao_grd(contrato)

        form = GrdForm(
            request.POST,
            contratos=contratos,
            configuracao=configuracao,
        )
        etapa = request.POST.get("etapa", "previa")
        previa = None
        erro = ""
        copias = {}
        cabecalho = None
        if form.is_valid():
            dados = form.cleaned_data
            digitados = _valores_digitados(form, configuracao)
            if etapa == "confirmar":
                try:
                    previa_atual = preparar_grd(dados["contrato"], dados["texto_codigos"])
                except DocumentosIndisponiveis as excecao:
                    previa_atual = {"aceitos": [], "recusados": []}
                    erro = str(excecao)
                copias, erro_copias = _copias_post(
                    request,
                    previa_atual,
                    configuracao.formatos_copias or [],
                    validar=True,
                )
                if erro_copias and not erro:
                    erro = erro_copias
                if erro:
                    previa = previa_atual
                else:
                    try:
                        resultado = criar_grd(
                            dados["contrato"],
                            request.user,
                            dados["data"],
                            dados["destinatario"],
                            dados["observacao"],
                            dados["texto_codigos"],
                            valores_digitados=digitados,
                            copias_por_emissao=copias,
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
            if previa is not None:
                cabecalho = dados_cabecalho_previa(
                    contrato, previa, dados["data"], digitados
                )
                copias, erro_copias = _copias_post(
                    request,
                    previa,
                    cabecalho["formatos_copias"],
                    validar=False,
                )
                if erro_copias and not erro:
                    erro = erro_copias
                _enriquecer_previa(previa, cabecalho, copias)

        return render(
            request,
            self.template_name,
            {
                "form": form,
                "contrato": contrato,
                "configuracao": configuracao,
                "previa": previa,
                "cabecalho": cabecalho,
                "erro": erro,
                "etapa": etapa,
            },
            status=400 if form.errors else 200,
        )


class DetalheGrdView(LoginRequiredMixin, View):
    template_name = "grds/detalhe.html"

    def get(self, request, contrato_id, grd_id):
        contrato = resolver_contrato(request.user, contrato_id)
        request.session["contrato_ativo_id"] = contrato.pk
        grd = get_object_or_404(
            Grd.objects.filter(contrato=contrato)
            .select_related("contrato", "criado_por")
            .prefetch_related("itens__emissao__documento"),
            pk=grd_id,
        )
        configuracao = garantir_configuracao_grd(contrato)
        formatos_copias = grd.formatos_copias or configuracao.formatos_copias or []
        itens = list(grd.itens.all())
        automaticos = [
            {"rotulo": "Data", "valor": grd.data.strftime("%d/%m/%Y")},
            {"rotulo": "Quantidade de documentos", "valor": str(len(itens))},
            {"rotulo": "Número", "valor": grd.rotulo()},
        ]
        campos_configurados = [
            {
                "rotulo": campo.rotulo,
                "valor": grd.campos_cabecalho.get(campo.chave, ""),
            }
            for campo in configuracao.campos.filter(habilitado=True)
        ]
        for item in itens:
            item.copias_impressao = [
                item.copias.get(formato, "") for formato in formatos_copias
            ]
        emitido_por_nome = grd.emitido_por_nome.strip()
        if not emitido_por_nome and grd.criado_por:
            emitido_por_nome = grd.criado_por.get_full_name().strip()
        return render(
            request,
            self.template_name,
            {
                "contrato": contrato,
                "grd": grd,
                "itens": itens,
                "url_lista": f"{reverse('grds:lista')}?contrato={contrato.pk}",
                "configuracao": configuracao,
                "logo_data_uri": _logo_data_uri(configuracao),
                "formatos_copias": formatos_copias,
                "campos_impressao": automaticos + campos_configurados,
                "emitido_por_nome": emitido_por_nome,
            },
        )


class ConfigurarGrdView(LoginRequiredMixin, View):
    template_name = "grds/configurar.html"

    def _contexto(self, contrato, configuracao, form, formset):
        return {
            "contrato": contrato,
            "configuracao": configuracao,
            "logo_data_uri": _logo_data_uri(configuracao),
            "form": form,
            "formset": formset,
        }

    def get(self, request):
        contrato = _contrato_ativo(request)
        if contrato is None:
            return _contratos_escolher()
        if not pode_configurar_grd(request.user, contrato):
            raise PermissionDenied
        configuracao = garantir_configuracao_grd(contrato)
        form = GrdConfiguracaoForm(instance=configuracao)
        formset = GrdCampoCabecalhoFormSet(instance=configuracao)
        return render(
            request,
            self.template_name,
            self._contexto(contrato, configuracao, form, formset),
        )

    def post(self, request):
        contrato = _contrato_ativo(request)
        if contrato is None:
            return _contratos_escolher()
        if not pode_configurar_grd(request.user, contrato):
            raise PermissionDenied
        configuracao = garantir_configuracao_grd(contrato)
        form = GrdConfiguracaoForm(
            request.POST, request.FILES, instance=configuracao
        )
        formset = GrdCampoCabecalhoFormSet(request.POST, instance=configuracao)
        if form.is_valid() and formset.is_valid():
            configuracao = form.save()
            formset.instance = configuracao
            formset.save()
            messages.success(request, "Configuração da GRD salva.")
            return redirect("grds:configurar")
        return render(
            request,
            self.template_name,
            self._contexto(contrato, configuracao, form, formset),
            status=400,
        )
