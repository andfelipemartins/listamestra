from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from core.perfil import ErroPerfil, perfil_de_dict
from contratos.models import Contrato, PerfilContrato
from documentos.models import Analise, Documento, Emissao

from .forms import ImportarIDForm, ImportarSituacaoPWForm
from .id_excel import (
    CATEGORIAS,
    ROTULOS_CATEGORIA,
    ErroFormatoID,
    LinhaPrevia,
    PreviaID,
    gerar_previa_id,
)
from .models import ImportacaoSituacao, IndiceDocumentos, ItemPrevisto
from .services import ErroAplicacaoID, aplicar_previa
from .situacao_pw import (
    ErroFormatoSituacaoPW,
    PreviaSituacaoPW,
    DocumentoPreviaPW,
    EmissaoPreviaPW,
    AnalisePreviaPW,
    LinhaInvalidaPW,
    HistoricoTruncadoPW,
    MudancaSituacaoPW,
    aplicar_previa_situacao_pw,
    gerar_previa_situacao_pw,
)


CHAVE_SESSAO = "previa_importacao_id"
CHAVE_SESSAO_SITUACAO = "previa_importacao_situacao_pw"
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
            f"ID {indice.codigo}, revisão {indice.revisao}, importado com "
            f"{previa.linhas_validas} linhas válidas e "
            f"{previa.linhas_fora} inválidas ou ilegíveis registradas.",
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


class ImportarSituacaoPWView(LoginRequiredMixin, UserPassesTestMixin, View):
    template_name = "importacoes/situacao_pw.html"
    raise_exception = True

    def test_func(self):
        return self.request.user.is_staff

    def get(self, request):
        request.session.pop(CHAVE_SESSAO_SITUACAO, None)
        return render(
            request,
            self.template_name,
            {
                "form": ImportarSituacaoPWForm(),
                "importacoes": ImportacaoSituacao.objects.select_related("contrato", "importado_por")[:20],
            },
        )

    def post(self, request):
        if request.POST.get("acao") == "confirmar":
            return self._confirmar(request)
        return self._prever(request)

    def _prever(self, request):
        form = ImportarSituacaoPWForm(request.POST, request.FILES)
        if not form.is_valid():
            return self._render_result(request, {"form": form})
        contrato = form.cleaned_data["contrato"]
        data_extracao = form.cleaned_data["data_extracao"]
        perfil_modelo = PerfilContrato.perfil_vigente(contrato, data_extracao)
        if perfil_modelo is None:
            form.add_error("contrato", "O contrato não tem perfil vigente na data da extração.")
            return self._render_result(request, {"form": form})
        try:
            arquivo = form.cleaned_data["arquivo"]
            previa = gerar_previa_situacao_pw(
                arquivo,
                nome_arquivo=arquivo.name,
                contrato_id=contrato.pk,
                perfil_id=perfil_modelo.pk,
                perfil=perfil_de_dict(perfil_modelo.definicao),
                data_extracao=data_extracao,
                documentos_existentes={
                    identificador: {"titulo": titulo}
                    for identificador, titulo in Documento.objects.filter(contrato=contrato).values_list(
                        "identificador_base", "titulo"
                    )
                },
                identificadores_previstos=list(ItemPrevisto.objects.filter(
                    indice__contrato=contrato,
                    indice__vigente=True,
                    excluido=False,
                ).values_list("documento__identificador_base", flat=True)),
                emissoes_existentes=list(Emissao.objects.filter(
                    documento__contrato=contrato
                ).values_list("documento__identificador_base", "revisao", "versao")),
                analises_existentes=list(Analise.objects.filter(
                    emissao__documento__contrato=contrato
                ).values_list(
                    "emissao__documento__identificador_base",
                    "emissao__revisao",
                    "emissao__versao",
                    "situacao",
                    "data_analise",
                    "origem",
                )),
                situacoes_vigentes=_situacoes_vigentes(contrato),
            )
        except (ErroFormatoSituacaoPW, ErroPerfil, ValueError) as erro:
            return self._render_result(request, {"form": form, "erro": str(erro)})

        request.session[CHAVE_SESSAO_SITUACAO] = {
            "usuario_id": request.user.pk,
            "previa": _serializar_previa_situacao(previa),
        }
        return self._render_result(
            request,
            {
                "form": form,
                "previa": previa,
                "contagens": [
                    ("Documentos", len(previa.documentos)),
                    ("Emissões novas", previa.emissoes_novas),
                    ("Análises explícitas novas", previa.analises_explicitas),
                    ("Análises deduzidas novas", previa.analises_deduzidas),
                    ("Mudanças de situação vigente", previa.situacoes_alteradas),
                    ("Fora do ID", previa.documentos_fora_do_id),
                    ("Históricos truncados", len(previa.historicos_truncados)),
                    ("Linhas inválidas", len(previa.linhas_invalidas)),
                ],
                "importacoes": ImportacaoSituacao.objects.select_related("contrato", "importado_por")[:20],
            },
        )

    def _render_result(self, request, context):
        template = self.template_name
        if request.headers.get("HX-Request") == "true":
            template = "importacoes/_resultado_situacao_pw.html"
        return render(request, template, context)

    def _confirmar(self, request):
        dados = request.session.get(CHAVE_SESSAO_SITUACAO)
        if not dados or dados.get("usuario_id") != request.user.pk:
            messages.error(request, "A prévia expirou. Envie o arquivo novamente.")
            return redirect("importar_situacao_pw")
        try:
            previa = _previsao_situacao_da_sessao(dados["previa"])
            contrato = get_object_or_404(Contrato, pk=previa.contrato_id)
            perfil_modelo = get_object_or_404(
                PerfilContrato,
                pk=previa.perfil_id,
                contrato=contrato,
            )
            vigente = PerfilContrato.perfil_vigente(contrato, previa.data_extracao)
            if vigente is None or vigente.pk != perfil_modelo.pk:
                raise ValueError("O perfil vigente mudou. Envie o arquivo e gere outra prévia.")
            importacao = aplicar_previa_situacao_pw(
                previa,
                contrato=contrato,
                perfil_modelo=perfil_modelo,
                usuario=request.user,
            )
        except (ValueError, KeyError, TypeError) as erro:
            messages.error(request, str(erro))
            return redirect("importar_situacao_pw")
        request.session.pop(CHAVE_SESSAO_SITUACAO, None)
        messages.success(
            request,
            f"Extração de {importacao.data_extracao:%d/%m/%Y} importada: "
            f"{importacao.documentos} documentos, {importacao.emissoes} emissões novas e "
            f"{importacao.linhas_invalidas} linhas inválidas registradas.",
        )
        return redirect("importar_situacao_pw")


def _situacoes_vigentes(contrato):
    resultado = {}
    documentos = Documento.objects.filter(contrato=contrato).prefetch_related("emissoes__analises")
    for documento in documentos:
        emissoes = sorted(documento.emissoes.all(), key=lambda item: (item.data_emissao, item.pk))
        if not emissoes:
            continue
        analises = sorted(
            emissoes[-1].analises.all(),
            key=lambda item: (item.data_analise or timezone.datetime.min.date(), item.registrado_em, item.pk),
        )
        if analises:
            resultado[documento.identificador_base] = analises[-1].situacao
    return resultado


def _serializar_previa_situacao(previa):
    def data(value):
        return value.isoformat() if value else None

    return {
        "contrato_id": previa.contrato_id,
        "perfil_id": previa.perfil_id,
        "data_extracao": data(previa.data_extracao),
        "arquivo_nome": previa.arquivo_nome,
        "documentos": [
            {
                "codigo_base": documento.codigo_base,
                "identificador_base": documento.identificador_base,
                "segmentos": documento.segmentos,
                "titulo": documento.titulo,
                "fora_do_id": documento.fora_do_id,
                "situacao_vigente": documento.situacao_vigente,
                "emissao_mais_recente": documento.emissao_mais_recente,
                "emissoes": [
                    {
                        "revisao": emissao.revisao,
                        "versao": emissao.versao,
                        "fase": emissao.fase,
                        "data_emissao": data(emissao.data_emissao),
                        "nome_arquivo": emissao.nome_arquivo,
                        "nova": emissao.nova,
                        "analises": [
                            {
                                "situacao": analise.situacao,
                                "data_analise": data(analise.data_analise),
                                "origem": analise.origem,
                                "observacao": analise.observacao,
                                "nova": analise.nova,
                            }
                            for analise in emissao.analises
                        ],
                    }
                    for emissao in documento.emissoes
                ],
            }
            for documento in previa.documentos
        ],
        "linhas_invalidas": [linha.__dict__ for linha in previa.linhas_invalidas],
        "historicos_truncados": [linha.__dict__ for linha in previa.historicos_truncados],
        "mudancas_situacao": [mudanca.__dict__ for mudanca in previa.mudancas_situacao],
    }


def _previsao_situacao_da_sessao(dados):
    from datetime import date

    documentos = []
    for documento in dados["documentos"]:
        emissoes = []
        for emissao in documento["emissoes"]:
            analises = tuple(
                AnalisePreviaPW(
                    situacao=analise["situacao"],
                    data_analise=date.fromisoformat(analise["data_analise"]) if analise["data_analise"] else None,
                    origem=analise["origem"],
                    observacao=analise["observacao"],
                    nova=analise["nova"],
                )
                for analise in emissao["analises"]
            )
            emissoes.append(
                EmissaoPreviaPW(
                    revisao=emissao["revisao"],
                    versao=emissao["versao"],
                    fase=emissao["fase"],
                    data_emissao=date.fromisoformat(emissao["data_emissao"]),
                    analises=analises,
                    nome_arquivo=emissao["nome_arquivo"],
                    nova=emissao["nova"],
                )
            )
        emissao_mais_recente = documento["emissao_mais_recente"]
        documentos.append(
            DocumentoPreviaPW(
                codigo_base=documento["codigo_base"],
                identificador_base=documento["identificador_base"],
                segmentos=documento["segmentos"],
                titulo=documento["titulo"],
                emissoes=tuple(emissoes),
                fora_do_id=documento["fora_do_id"],
                situacao_vigente=documento["situacao_vigente"],
                emissao_mais_recente=tuple(emissao_mais_recente) if emissao_mais_recente else None,
            )
        )
    return PreviaSituacaoPW(
        contrato_id=dados["contrato_id"],
        perfil_id=dados["perfil_id"],
        data_extracao=date.fromisoformat(dados["data_extracao"]),
        arquivo_nome=dados["arquivo_nome"],
        documentos=tuple(documentos),
        linhas_invalidas=tuple(LinhaInvalidaPW(**linha) for linha in dados["linhas_invalidas"]),
        historicos_truncados=tuple(HistoricoTruncadoPW(**linha) for linha in dados["historicos_truncados"]),
        mudancas_situacao=tuple(MudancaSituacaoPW(**linha) for linha in dados["mudancas_situacao"]),
    )
