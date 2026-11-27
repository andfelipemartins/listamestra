import csv
from datetime import date
from io import StringIO

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views import View

from contas.models import Usuario
from contratos.models import Contrato
from .servicos import ACOES, carregar_eventos


class AtividadeView(LoginRequiredMixin, View):
    template_name = "registro/atividade.html"
    page_size = 50

    def get(self, request):
        contratos = list(_contratos_acessiveis(request))
        if not contratos:
            raise PermissionDenied
        contratos_por_id = {str(contrato.pk): contrato for contrato in contratos}
        selecionado = request.GET.get("contrato")
        if selecionado:
            contrato = contratos_por_id.get(selecionado)
            if contrato is None:
                if not request.user.is_staff:
                    raise PermissionDenied
                contrato = get_object_or_404(Contrato, pk=selecionado)
        else:
            contrato = contratos[0]

        eventos = carregar_eventos(contrato)
        pessoas = _opcoes_pessoas(eventos)
        filtros = {
            "contrato": str(contrato.pk),
            "pessoa": request.GET.get("pessoa", ""),
            "acao": request.GET.get("acao", ""),
            "de": request.GET.get("de", ""),
            "ate": request.GET.get("ate", ""),
            "codigo": request.GET.get("codigo", "").strip(),
        }
        eventos_filtrados = _filtrar(eventos, filtros)
        if request.GET.get("formato") == "csv":
            return _resposta_csv(contrato, eventos_filtrados)

        chave_evento = request.GET.get("evento", "")
        evento_detalhe = next(
            (evento for evento in eventos if evento["chave"] == chave_evento), None
        )
        if chave_evento and evento_detalhe is None:
            from django.http import Http404

            raise Http404

        for evento in eventos_filtrados:
            evento["data_hora_local"] = timezone.localtime(evento["data_hora"])
            evento["url_detalhe"] = _url_com_parametros(request.GET, "evento", evento["chave"])
            if evento.get("documento_id"):
                evento["url_documento"] = reverse(
                    "documento_pasta", args=(contrato.pk, evento["documento_id"])
                )
            if evento["link_recusadas"]:
                evento["url_recusadas"] = reverse("linhas_recusadas", args=(contrato.pk,))
            if evento.get("grd_id"):
                evento["url_grd"] = reverse(
                    "grds:detalhe", args=(evento["grd_contrato_id"], evento["grd_id"])
                )

        if evento_detalhe is not None:
            evento_detalhe["data_hora_local"] = timezone.localtime(evento_detalhe["data_hora"])
            if evento_detalhe.get("documento_id"):
                evento_detalhe["url_documento"] = reverse(
                    "documento_pasta", args=(contrato.pk, evento_detalhe["documento_id"])
                )
            if evento_detalhe["link_recusadas"]:
                evento_detalhe["url_recusadas"] = reverse("linhas_recusadas", args=(contrato.pk,))
            if evento_detalhe.get("grd_id"):
                evento_detalhe["url_grd"] = reverse(
                    "grds:detalhe",
                    args=(evento_detalhe["grd_contrato_id"], evento_detalhe["grd_id"]),
                )

        pagina = Paginator(eventos_filtrados, self.page_size).get_page(request.GET.get("pagina"))
        links_paginas = [
            {
                "numero": numero,
                "url": "" if numero == pagina.number else _url_sem_parametro(
                    request.GET, "evento", "pagina", numero
                ),
                "atual": numero == pagina.number,
            }
            for numero in pagina.paginator.page_range
        ]
        anterior_url = (
            _url_sem_parametro(request.GET, "evento", "pagina", pagina.previous_page_number())
            if pagina.has_previous()
            else ""
        )
        proxima_url = (
            _url_sem_parametro(request.GET, "evento", "pagina", pagina.next_page_number())
            if pagina.has_next()
            else ""
        )

        contexto = {
            "contrato": contrato,
            "contratos": contratos,
            "pessoas": pessoas,
            "acoes": ACOES,
            "filtros": filtros,
            "pagina": pagina,
            "links_paginas": links_paginas,
            "anterior_url": anterior_url,
            "proxima_url": proxima_url,
            "evento_detalhe": evento_detalhe,
            "url_lista": _url_sem_parametro(request.GET, "evento"),
            "url_csv": _url_csv(request.GET),
            "total_filtrado": len(eventos_filtrados),
        }
        return render(request, self.template_name, contexto)


def _resposta_csv(contrato, eventos):
    arquivo = StringIO(newline="")
    escritor = csv.writer(arquivo, delimiter=";", lineterminator="\r\n")
    escritor.writerow(
        ("Data e hora", "Pessoa", "Ação", "Evento", "Código do documento", "Resumo")
    )
    for evento in eventos:
        data_hora_local = timezone.localtime(evento["data_hora"])
        escritor.writerow(
            (
                data_hora_local.strftime("%d/%m/%Y %H:%M"),
                evento["usuario_nome"],
                evento["acao_rotulo"],
                evento["entidade"],
                evento.get("codigo", ""),
                evento["resumo"],
            )
        )

    identificador = slugify(contrato.codigo_interno) or f"contrato-{contrato.pk}"
    nome_arquivo = f"atividade-{identificador}-{timezone.localdate().isoformat()}.csv"
    resposta = HttpResponse(
        arquivo.getvalue().encode("utf-8-sig"),
        content_type="text/csv; charset=utf-8",
    )
    resposta["Content-Disposition"] = f'attachment; filename="{nome_arquivo}"'
    return resposta


def _contratos_acessiveis(request):
    usuario = request.user
    if not usuario.is_active:
        return Contrato.objects.none()
    if usuario.is_staff or usuario.is_superuser:
        return Contrato.objects.all()
    return Contrato.objects.filter(
        participacoes__usuario=usuario,
        participacoes__ativo=True,
        participacoes__papel=Usuario.Perfil.ADMIN,
    ).distinct()


def _opcoes_pessoas(eventos):
    pessoas = {}
    tem_sistema = False
    for evento in eventos:
        if evento["usuario_id"] is None:
            tem_sistema = True
        else:
            pessoas[str(evento["usuario_id"])] = evento["usuario_nome"]
    opcoes = [(chave, pessoas[chave]) for chave in sorted(pessoas, key=lambda valor: pessoas[valor].casefold())]
    if tem_sistema:
        opcoes.append(("sistema", "Sistema"))
    return opcoes


def _filtrar(eventos, filtros):
    pessoa = filtros["pessoa"]
    acao = filtros["acao"]
    codigo = filtros["codigo"].casefold()
    data_de = _data(filtros["de"])
    data_ate = _data(filtros["ate"])
    resultado = []
    for evento in eventos:
        if pessoa and (
            (pessoa == "sistema" and evento["usuario_id"] is not None)
            or (pessoa != "sistema" and str(evento["usuario_id"]) != pessoa)
        ):
            continue
        if acao and evento["acao"] != acao:
            continue
        if codigo and codigo not in evento["codigo"].casefold():
            continue
        data_evento = timezone.localtime(evento["data_hora"]).date()
        if data_de and data_evento < data_de:
            continue
        if data_ate and data_evento > data_ate:
            continue
        resultado.append(evento)
    return resultado


def _data(valor):
    try:
        return date.fromisoformat(valor) if valor else None
    except ValueError:
        return None


def _url_com_parametros(parametros, nome, valor):
    consulta = parametros.copy()
    consulta.pop("evento", None)
    consulta[nome] = str(valor)
    return f"{reverse('atividade')}?{consulta.urlencode()}"


def _url_sem_parametro(parametros, remover, nome=None, valor=None):
    consulta = parametros.copy()
    consulta.pop(remover, None)
    if nome:
        consulta[nome] = str(valor)
    return f"{reverse('atividade')}?{consulta.urlencode()}" if consulta else reverse("atividade")


def _url_csv(parametros):
    consulta = parametros.copy()
    consulta.pop("evento", None)
    consulta.pop("pagina", None)
    consulta["formato"] = "csv"
    return f"{reverse('atividade')}?{consulta.urlencode()}"
