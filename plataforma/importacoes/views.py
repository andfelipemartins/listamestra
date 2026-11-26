from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from core.perfil import ErroPerfil, perfil_de_dict
from core.perfil.codigo import ErroCodigo, interpretar
from contas.models import Usuario
from contratos.models import Contrato, EscopoContrato, Participacao, PerfilContrato
from documentos.models import Analise, Documento, Emissao

from .forms import (
    ImportarCronogramaForm,
    ImportarIDForm,
    ImportarSituacaoPadraoForm,
    ImportarSituacaoPWForm,
)
from .id_excel import (
    CATEGORIAS,
    ROTULOS_CATEGORIA,
    ErroFormatoID,
    FORMATOS_ID,
    LinhaPrevia,
    PreviaID,
    gerar_previa_linhas_recusadas,
    gerar_previa_id,
)
from .models import InconsistenciaImportacao, ImportacaoID, ImportacaoSituacao, IndiceDocumentos, ItemPrevisto
from .services import ErroAplicacaoID, aplicar_previa, resumir_substituicao
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
    gerar_previa_linhas_recusadas_situacao_pw,
    gerar_previa_situacao_pw,
)
from .cronograma import (
    ErroAplicacaoCronograma,
    ErroFormatoCronograma,
    PreviaCronograma,
    LinhaCronograma,
    aplicar_previa_cronograma,
    gerar_previa_cronograma,
)
from .models import ImportacaoCronograma
from .situacao_padrao import (
    ErroFormatoSituacaoPadrao,
    CampoIgnorado,
    LinhaSituacaoPadrao,
    PreviaSituacaoPadrao,
    aplicar_previa_situacao_padrao,
    gerar_modelo_situacao_padrao,
    gerar_previa_situacao_padrao,
)


CHAVE_SESSAO = "previa_importacao_id"
CHAVE_SESSAO_SITUACAO = "previa_importacao_situacao_pw"
CHAVE_SESSAO_REPROCESSAMENTO = "previa_reprocessamento_recusadas"
CHAVE_SESSAO_CRONOGRAMA = "previa_importacao_cronograma"
CHAVE_SESSAO_SITUACAO_PADRAO = "previa_importacao_situacao_padrao"
PREFIXO_ARQUIVO_SITUACAO_PADRAO = "[Planilha padrão] "


class LinhasRecusadasView(LoginRequiredMixin, View):
    template_name = "importacoes/recusadas.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        contrato = get_object_or_404(Contrato, pk=kwargs["contrato_id"])
        if not request.user.is_staff and not Participacao.objects.filter(
            usuario=request.user,
            contrato=contrato,
            ativo=True,
        ).exists():
            raise PermissionDenied
        self.pode_reprocessar = request.user.is_staff or Participacao.objects.filter(
            usuario=request.user,
            contrato=contrato,
            ativo=True,
            papel=Usuario.Perfil.ADMIN,
        ).exists()
        if request.method == "POST" and not self.pode_reprocessar:
            raise PermissionDenied
        self.contrato = contrato
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, contrato_id):
        dados_sessao = request.session.get(CHAVE_SESSAO_REPROCESSAMENTO)
        previa = None
        importacao_previa = None
        tipo_previa = "id"
        codigos_reprocessados = []
        if (
            dados_sessao
            and dados_sessao.get("usuario_id") == request.user.pk
            and dados_sessao.get("contrato_id") == self.contrato.pk
        ):
            tipo_previa = dados_sessao.get("tipo", "id")
            if tipo_previa == "situacao_pw":
                previa = _previsao_situacao_da_sessao(dados_sessao["previa"])
                importacao_previa = get_object_or_404(
                    ImportacaoSituacao,
                    pk=dados_sessao["importacao_id"],
                    contrato=self.contrato,
                )
                codigos_reprocessados = dados_sessao.get("codigos_reprocessados", [])
            else:
                previa = _previsao_da_sessao(dados_sessao)
                importacao_previa = get_object_or_404(
                    ImportacaoID.objects.select_related("indice"),
                    pk=dados_sessao["importacao_id"],
                    contrato=self.contrato,
                )
        return render(
            request,
            self.template_name,
            _contexto_recusadas(
                self.contrato,
                previa=previa,
                importacao_previa=importacao_previa,
                tipo_previa=tipo_previa,
                codigos_reprocessados=codigos_reprocessados,
                pode_reprocessar=self.pode_reprocessar,
            ),
        )

    def post(self, request, contrato_id):
        acao = request.POST.get("acao")
        if acao == "confirmar_reprocessamento":
            if request.session.get(CHAVE_SESSAO_REPROCESSAMENTO, {}).get("tipo") == "situacao_pw":
                return self._confirmar_situacao(request)
            return self._confirmar(request)
        if request.POST.get("importacao_situacao_id"):
            return self._prever_situacao(request)
        return self._prever(request)

    def _prever(self, request):
        importacao = get_object_or_404(
            ImportacaoID.objects.select_related("indice"),
            pk=request.POST.get("importacao_id"),
            contrato=self.contrato,
        )
        inconsistencias = list(
            importacao.inconsistencias.filter(resolvida_em__isnull=True).order_by("numero_linha", "pk")
        )
        perfil_modelo = PerfilContrato.perfil_vigente(self.contrato, timezone.localdate())
        if perfil_modelo is None:
            messages.error(request, "O contrato não tem perfil vigente para a data de hoje.")
            return redirect("linhas_recusadas", contrato_id=self.contrato.pk)
        try:
            perfil = perfil_de_dict(perfil_modelo.definicao)
            previa = gerar_previa_linhas_recusadas(
                inconsistencias,
                contrato_id=self.contrato.pk,
                perfil_id=perfil_modelo.pk,
                perfil=perfil,
                documentos_existentes=list(
                    Documento.objects.filter(contrato=self.contrato).values_list(
                        "identificador_base", "titulo"
                    )
                ),
            )
        except (ErroFormatoID, ErroPerfil, ValueError) as erro:
            messages.error(request, str(erro))
            return redirect("linhas_recusadas", contrato_id=self.contrato.pk)

        request.session[CHAVE_SESSAO_REPROCESSAMENTO] = {
            "tipo": "id",
            "usuario_id": request.user.pk,
            "contrato_id": self.contrato.pk,
            "perfil_id": perfil_modelo.pk,
            "importacao_id": importacao.pk,
            "inconsistencias_ids": [item.pk for item in inconsistencias],
            "fonte": previa.fonte,
            "codigo_indice": previa.codigo_indice,
            "revisao": previa.revisao,
            "arquivo_nome": previa.arquivo_nome,
            "formato": previa.formato,
            "linhas": [linha.__dict__ for linha in previa.linhas],
        }
        return render(
            request,
            self.template_name,
            _contexto_recusadas(
                self.contrato,
                previa=previa,
                importacao_previa=importacao,
                tipo_previa="id",
                pode_reprocessar=self.pode_reprocessar,
            ),
        )

    def _prever_situacao(self, request):
        importacao = get_object_or_404(
            ImportacaoSituacao,
            pk=request.POST.get("importacao_situacao_id"),
            contrato=self.contrato,
        )
        inconsistencias = list(
            importacao.inconsistencias.filter(resolvida_em__isnull=True).order_by("numero_linha", "pk")
        )
        perfil_modelo = PerfilContrato.perfil_vigente(self.contrato, timezone.localdate())
        if perfil_modelo is None:
            messages.error(request, "O contrato não tem perfil vigente para a data de hoje.")
            return redirect("linhas_recusadas", contrato_id=self.contrato.pk)

        try:
            perfil = perfil_de_dict(perfil_modelo.definicao)
            dados_existentes = _dados_existentes_situacao(self.contrato)
            com_dados = [item for item in inconsistencias if item.dados_linha]
            if com_dados:
                previa = gerar_previa_linhas_recusadas_situacao_pw(
                    com_dados,
                    nome_arquivo=importacao.arquivo_nome,
                    contrato_id=self.contrato.pk,
                    perfil_id=perfil_modelo.pk,
                    perfil=perfil,
                    data_extracao=importacao.data_extracao,
                    **dados_existentes,
                )
            else:
                previa = PreviaSituacaoPW(
                    contrato_id=self.contrato.pk,
                    perfil_id=perfil_modelo.pk,
                    data_extracao=importacao.data_extracao,
                    arquivo_nome=importacao.arquivo_nome,
                    documentos=(),
                )

            codigos_reprocessados = {
                documento.codigo_base
                for documento in previa.documentos
            }
            codigos_reprocessados.update(
                documento.identificador_base
                for documento in previa.documentos
            )
            for item in inconsistencias:
                if item.dados_linha or not item.codigo_lido:
                    continue
                interpretado = interpretar(perfil, item.codigo_lido)
                if not isinstance(interpretado, ErroCodigo):
                    codigos_reprocessados.add(item.codigo_lido)
        except (ErroFormatoSituacaoPW, ErroPerfil, ValueError) as erro:
            messages.error(request, str(erro))
            return redirect("linhas_recusadas", contrato_id=self.contrato.pk)

        request.session[CHAVE_SESSAO_REPROCESSAMENTO] = {
            "tipo": "situacao_pw",
            "usuario_id": request.user.pk,
            "contrato_id": self.contrato.pk,
            "perfil_id": perfil_modelo.pk,
            "importacao_id": importacao.pk,
            "inconsistencias_ids": [item.pk for item in inconsistencias],
            "codigos_reprocessados": sorted(codigos_reprocessados),
            "previa": _serializar_previa_situacao(previa),
        }
        return render(
            request,
            self.template_name,
            _contexto_recusadas(
                self.contrato,
                previa=previa,
                importacao_previa=importacao,
                tipo_previa="situacao_pw",
                codigos_reprocessados=codigos_reprocessados,
                pode_reprocessar=self.pode_reprocessar,
            ),
        )

    def _confirmar(self, request):
        dados = request.session.get(CHAVE_SESSAO_REPROCESSAMENTO)
        if (
            not dados
            or dados.get("usuario_id") != request.user.pk
            or dados.get("contrato_id") != self.contrato.pk
        ):
            messages.error(request, "A prévia expirou. Gere uma nova prévia das linhas recusadas.")
            return redirect("linhas_recusadas", contrato_id=self.contrato.pk)
        try:
            previa = _previsao_da_sessao(dados)
            importacao = get_object_or_404(
                ImportacaoID.objects.select_related("indice"),
                pk=dados["importacao_id"],
                contrato=self.contrato,
            )
            perfil_modelo = get_object_or_404(
                PerfilContrato,
                pk=dados["perfil_id"],
                contrato=self.contrato,
            )
            perfil_vigente = PerfilContrato.perfil_vigente(self.contrato, timezone.localdate())
            if perfil_vigente is None or perfil_vigente.pk != perfil_modelo.pk:
                raise ErroAplicacaoID("O perfil vigente mudou. Gere uma nova prévia.")
            inconsistencias = list(
                InconsistenciaImportacao.objects.filter(
                    pk__in=dados["inconsistencias_ids"],
                    importacao_id=importacao,
                )
            )
            if len(inconsistencias) != len(dados["inconsistencias_ids"]):
                raise ErroAplicacaoID("As linhas da prévia não pertencem mais à importação original.")
            indice = aplicar_previa(
                previa,
                contrato=self.contrato,
                perfil_modelo=perfil_modelo,
                usuario=request.user,
                inconsistencias_existentes=inconsistencias,
            )
        except (ErroAplicacaoID, ErroPerfil, ValueError, KeyError, TypeError) as erro:
            messages.error(request, str(erro))
            return redirect("linhas_recusadas", contrato_id=self.contrato.pk)
        request.session.pop(CHAVE_SESSAO_REPROCESSAMENTO, None)
        validas = previa.linhas_validas
        recusadas = previa.linhas_fora
        messages.success(
            request,
            f"{validas} linhas reprocessadas em {indice.codigo}, revisão {indice.revisao}; "
            f"{recusadas} continuam recusadas.",
        )
        return redirect("linhas_recusadas", contrato_id=self.contrato.pk)

    def _confirmar_situacao(self, request):
        dados = request.session.get(CHAVE_SESSAO_REPROCESSAMENTO)
        if (
            not dados
            or dados.get("usuario_id") != request.user.pk
            or dados.get("contrato_id") != self.contrato.pk
        ):
            messages.error(request, "A prévia expirou. Gere uma nova prévia das linhas recusadas.")
            return redirect("linhas_recusadas", contrato_id=self.contrato.pk)
        try:
            previa = _previsao_situacao_da_sessao(dados["previa"])
            importacao = get_object_or_404(
                ImportacaoSituacao,
                pk=dados["importacao_id"],
                contrato=self.contrato,
            )
            perfil_modelo = get_object_or_404(
                PerfilContrato,
                pk=dados["perfil_id"],
                contrato=self.contrato,
            )
            vigente = PerfilContrato.perfil_vigente(self.contrato, timezone.localdate())
            if vigente is None or vigente.pk != perfil_modelo.pk:
                raise ValueError("O perfil vigente mudou. Gere uma nova prévia.")
            inconsistencias = list(
                InconsistenciaImportacao.objects.filter(
                    pk__in=dados["inconsistencias_ids"],
                    importacao_situacao=importacao,
                    resolvida_em__isnull=True,
                )
            )
            if len(inconsistencias) != len(dados["inconsistencias_ids"]):
                raise ValueError("As linhas recusadas não pertencem mais à importação original.")
            aplicar_previa_situacao_pw(
                previa,
                contrato=self.contrato,
                perfil_modelo=perfil_modelo,
                usuario=request.user,
                inconsistencias_existentes=inconsistencias,
                codigos_reprocessados=dados.get("codigos_reprocessados", ()),
            )
        except (ErroPerfil, ValueError, KeyError, TypeError) as erro:
            messages.error(request, str(erro))
            return redirect("linhas_recusadas", contrato_id=self.contrato.pk)
        request.session.pop(CHAVE_SESSAO_REPROCESSAMENTO, None)
        resolvidas = InconsistenciaImportacao.objects.filter(
            pk__in=dados["inconsistencias_ids"],
            resolvida_em__isnull=False,
        ).count()
        pendentes = len(dados["inconsistencias_ids"]) - resolvidas
        messages.success(
            request,
            f"{resolvidas} linhas reavaliadas pelo perfil vigente; {pendentes} continuam recusadas.",
        )
        return redirect("linhas_recusadas", contrato_id=self.contrato.pk)


def _contexto_recusadas(
    contrato,
    *,
    previa=None,
    importacao_previa=None,
    tipo_previa="id",
    codigos_reprocessados=(),
    pode_reprocessar=False,
):
    consulta_id = (
        ImportacaoID.objects.filter(
            contrato=contrato,
            inconsistencias__resolvida_em__isnull=True,
        )
        .select_related("indice")
        .distinct()
        .order_by("-importado_em", "-pk")
    )
    importacoes = []
    for importacao in consulta_id:
        inconsistencias = list(
            importacao.inconsistencias.filter(resolvida_em__isnull=True).order_by("numero_linha", "pk")
        )
        importacoes.append({
            "importacao": importacao,
            "inconsistencias": inconsistencias,
            "grupos": _grupos_recusadas(inconsistencias, importacao.indice.fonte),
        })

    consulta_situacao = (
        ImportacaoSituacao.objects.filter(
            contrato=contrato,
            inconsistencias__resolvida_em__isnull=True,
        )
        .distinct()
        .order_by("-importado_em", "-pk")
    )
    importacoes_situacao = []
    for importacao in consulta_situacao:
        inconsistencias = list(
            importacao.inconsistencias.filter(resolvida_em__isnull=True).order_by("numero_linha", "pk")
        )
        importacoes_situacao.append({
            "importacao": importacao,
            "inconsistencias": inconsistencias,
                "grupos": _grupos_recusadas(inconsistencias, "situacao_pw"),
        })

    perfil_modelo = PerfilContrato.perfil_vigente(contrato, timezone.localdate())
    perfil_codigo = None
    if perfil_modelo is not None:
        try:
            perfil_codigo = perfil_de_dict(perfil_modelo.definicao)
        except (ErroPerfil, TypeError, ValueError):
            pass
    documentos_por_identificador = {
        identificador.upper(): documento_id
        for identificador, documento_id in Documento.objects.filter(contrato=contrato).values_list(
            "identificador_base", "pk"
        )
    }
    linhas_recusadas = (
        linha
        for item in (*importacoes, *importacoes_situacao)
        for grupo in item["grupos"]
        for linha in grupo["linhas"]
    )
    for linha in linhas_recusadas:
        codigo_lido = (linha.codigo_lido or "").strip()
        identificador_base = codigo_lido.upper()
        if perfil_codigo is not None and codigo_lido:
            interpretado = interpretar(perfil_codigo, codigo_lido)
            if not isinstance(interpretado, ErroCodigo):
                identificador_base = interpretado.identificador_base.upper()
        linha.documento_link_id = documentos_por_identificador.get(identificador_base)

    codigos_reprocessados = set(codigos_reprocessados)
    if previa and tipo_previa == "situacao_pw":
        codigos_reprocessados.update(documento.codigo_base for documento in previa.documentos)
        codigos_reprocessados.update(documento.identificador_base for documento in previa.documentos)
        validas = 0
        linhas_fora = len(previa.linhas_invalidas)
        if importacao_previa:
            abertas = list(importacao_previa.inconsistencias.filter(resolvida_em__isnull=True))
            aceitas = [
                item for item in abertas
                if item.codigo_lido.strip().upper()
                in {codigo.strip().upper() for codigo in codigos_reprocessados}
            ]
            validas = len(aceitas)
            linhas_fora = max(linhas_fora, len(abertas) - len(aceitas))
    else:
        validas = previa.linhas_validas if previa else 0
        linhas_fora = previa.linhas_fora if previa else 0

    return {
        "contrato": contrato,
        "importacoes": importacoes,
        "importacoes_situacao": importacoes_situacao,
        "total_recusadas": sum(
            len(item["inconsistencias"])
            for item in (*importacoes, *importacoes_situacao)
        ),
        "previa": previa,
        "importacao_previa": importacao_previa,
        "tipo_previa": tipo_previa,
        "pode_reprocessar": pode_reprocessar,
        "linhas_validas": validas,
        "linhas_fora": linhas_fora,
        "codigos_reprocessados": sorted(codigos_reprocessados),
    }


def _grupos_recusadas(inconsistencias, origem):
    grupos = {}
    for inconsistencia in inconsistencias:
        categoria = inconsistencia.categoria
        if not categoria:
            categoria = "codigos_invalidos" if origem == "situacao_pw" else "linhas_ilegiveis"
        if categoria not in grupos:
            grupos[categoria] = {
                "categoria": categoria,
                "titulo": _rotulo_recusa(categoria, origem),
                "instrucao": _instrucao_recusa(categoria, origem),
                "linhas": [],
            }
        grupos[categoria]["linhas"].append(inconsistencia)
    return list(grupos.values())


def _rotulo_recusa(categoria, origem=""):
    if categoria == "linhas_ilegiveis":
        if origem == IndiceDocumentos.Fonte.EXTRACAO_PW:
            return "Extração defeituosa do PW"
        return "Linha ilegível"
    return {
        "atributos_divergentes": "Atributo do PW divergente do Name",
        "codigos_invalidos": "Código inválido",
        "dados_invalidos": "Dados do PW inválidos",
    }.get(categoria, "Linha recusada")


def _instrucao_recusa(categoria, origem=""):
    if categoria == "linhas_ilegiveis":
        if origem == IndiceDocumentos.Fonte.EXTRACAO_PW:
            return "Reextraia essa disciplina e importe de novo."
        return "Corrija os dados na planilha e importe de novo."
    return {
        "atributos_divergentes": "Confira no PW qual está certo, corrija e reextraia a planilha e importe de novo.",
        "codigos_invalidos": "Corrija o código na planilha ou no PW e importe de novo.",
        "dados_invalidos": "Corrija os dados na planilha ou no PW e importe de novo.",
    }.get(categoria, "Corrija a linha na planilha ou no PW e importe de novo.")


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
            {
                "form": ImportarIDForm(
                    initial={"contrato": request.GET.get("contrato", "")}
                ),
                "indices": _indices_para_listagem(),
            },
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

        indices_substituidos = list(form.cleaned_data["substituidos"])
        if indices_substituidos and previa.fonte != IndiceDocumentos.Fonte.EXCEL_ID:
            form.add_error(
                "substituidos",
                "A substituição está disponível apenas para IDs importados por Excel.",
            )
            return self._render_result(request, {"form": form})
        if any(
            indice.codigo == previa.codigo_indice
            and indice.revisao == previa.revisao
            for indice in indices_substituidos
        ):
            form.add_error("substituidos", "Um ID não pode substituir a si mesmo.")
            return self._render_result(request, {"form": form})
        if indices_substituidos and any(
            linha.categoria in {"codigos_invalidos", "atributos_divergentes", "linhas_ilegiveis"}
            for linha in previa.linhas
        ):
            form.add_error(
                "substituidos",
                "Corrija as linhas recusadas antes de substituir um ID vigente.",
            )
            return self._render_result(request, {"form": form})
        substituicao = (
            resumir_substituicao(previa, indices_substituidos)
            if indices_substituidos
            else None
        )

        request.session[CHAVE_SESSAO] = {
            "usuario_id": request.user.pk,
            "contrato_id": previa.contrato_id,
            "perfil_id": previa.perfil_id,
            "fonte": previa.fonte,
            "codigo_indice": previa.codigo_indice,
            "revisao": previa.revisao,
            "fase": form.cleaned_data["fase"].strip(),
            "escopos_ids": [escopo.pk for escopo in form.cleaned_data["escopos"]],
            "substituir_ids": [indice.pk for indice in indices_substituidos],
            "novo_escopo": form.cleaned_data["novo_escopo"],
            "arquivo_nome": previa.arquivo_nome,
            "formato": previa.formato,
            "linhas": [linha.__dict__ for linha in previa.linhas],
        }
        return self._render_result(
            request,
            {
                "form": form,
                "previa": previa,
                "substituicao": substituicao,
                "indices_substituidos": indices_substituidos,
                "contagens": [
                    (ROTULOS_CATEGORIA[categoria], previa.contagens[categoria])
                    for categoria in CATEGORIAS
                ],
                "indices": _indices_para_listagem(),
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
            escopos_ids = [int(pk) for pk in dados.get("escopos_ids", [])]
            if len(set(escopos_ids)) != len(escopos_ids):
                raise ErroAplicacaoID("A prévia contém escopos repetidos. Gere uma nova prévia.")
            escopos = list(
                EscopoContrato.objects.filter(
                    contrato=contrato,
                    pk__in=escopos_ids,
                ).order_by("nome")
            )
            if len(escopos) != len(escopos_ids):
                raise ErroAplicacaoID(
                    "Um dos escopos da prévia não pertence mais ao contrato. Gere uma nova prévia."
                )
            novo_escopo = dados.get("novo_escopo", "").strip()
            substituir_ids = [int(pk) for pk in dados.get("substituir_ids", [])]
            if len(set(substituir_ids)) != len(substituir_ids):
                raise ErroAplicacaoID("A prévia contém IDs substituídos repetidos. Gere uma nova prévia.")
            indices_substituidos = list(
                IndiceDocumentos.objects.filter(
                    pk__in=substituir_ids,
                    contrato=contrato,
                    fonte=IndiceDocumentos.Fonte.EXCEL_ID,
                    vigente=True,
                    substituido_por__isnull=True,
                ).order_by("pk")
            )
            if len(indices_substituidos) != len(substituir_ids):
                raise ErroAplicacaoID(
                    "Um ID selecionado não está mais vigente ou não pertence a este contrato. Gere nova prévia."
                )
            substituicao = (
                resumir_substituicao(previa, indices_substituidos)
                if indices_substituidos
                else None
            )
            with transaction.atomic():
                if novo_escopo:
                    escopo, _ = EscopoContrato.objects.get_or_create(
                        contrato=contrato,
                        nome__iexact=novo_escopo,
                        defaults={"nome": novo_escopo},
                    )
                    escopos.append(escopo)
                indice = aplicar_previa(
                    previa,
                    contrato=contrato,
                    perfil_modelo=perfil_modelo,
                    usuario=request.user,
                    substituir_ids=substituir_ids,
                )
                fase = dados.get("fase", "").strip()
                if fase and indice.fase != fase:
                    indice.fase = fase
                    indice._history_user = request.user
                    indice._change_reason = f"importacao_id:{indice.pk}:fase"
                    indice.save(update_fields=("fase",))
                indice._history_user = request.user
                indice._change_reason = f"importacao_id:{indice.pk}:escopos"
                indice.escopos.set(escopos)
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
        if substituicao and substituicao["codigos_com_movimentacao"]:
            messages.warning(
                request,
                "Aviso: código saiu do ID vigente e possui movimentação: "
                + ", ".join(substituicao["codigos_com_movimentacao"])
                + ".",
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


def _indices_para_listagem():
    indices = list(
        IndiceDocumentos.objects.select_related("contrato", "substituido_por")
        .order_by("-importado_em", "-pk")[:20]
    )
    ids_substituidos = [indice.pk for indice in indices if indice.substituido_por_id]
    historicos = IndiceDocumentos.history.model.objects.filter(
        id__in=ids_substituidos,
        vigente=False,
    ).exclude(substituido_por__isnull=True).order_by("-history_date")
    por_indice = {}
    for historico in historicos:
        por_indice.setdefault(historico.id, historico)
    for indice in indices:
        historico = por_indice.get(indice.pk)
        indice.substituido_em = historico.history_date if historico else None
        indice.substituido_por_usuario = historico.history_user if historico else None
    return indices


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
                "importacoes": ImportacaoSituacao.objects.select_related("contrato", "importado_por")
                .exclude(arquivo_nome__startswith=PREFIXO_ARQUIVO_SITUACAO_PADRAO)[:20],
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
                **_dados_existentes_situacao(contrato),
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
                "importacoes": ImportacaoSituacao.objects.select_related("contrato", "importado_por")
                .exclude(arquivo_nome__startswith=PREFIXO_ARQUIVO_SITUACAO_PADRAO)[:20],
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


def _dados_existentes_situacao(contrato):
    return {
        "documentos_existentes": {
            identificador: {"titulo": titulo}
            for identificador, titulo in Documento.objects.filter(contrato=contrato).values_list(
                "identificador_base", "titulo"
            )
        },
        "identificadores_previstos": list(ItemPrevisto.objects.filter(
            indice__contrato=contrato,
            indice__vigente=True,
            excluido=False,
        ).values_list("documento__identificador_base", flat=True)),
        "emissoes_existentes": list(Emissao.objects.filter(
            documento__contrato=contrato
        ).values_list("documento__identificador_base", "revisao", "versao")),
        "analises_existentes": list(Analise.objects.filter(
            emissao__documento__contrato=contrato
        ).values_list(
            "emissao__documento__identificador_base",
            "emissao__revisao",
            "emissao__versao",
            "situacao",
            "data_analise",
            "origem",
        )),
        "situacoes_vigentes": _situacoes_vigentes(contrato),
    }


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


class PermissaoImportarSituacaoPadraoMixin(LoginRequiredMixin, UserPassesTestMixin):
    raise_exception = True

    def test_func(self):
        return self.request.user.is_staff or Participacao.objects.filter(
            usuario=self.request.user,
            ativo=True,
            papel__in=(Usuario.Perfil.ADMIN, Usuario.Perfil.EQUIPE),
        ).exists()


class BaixarModeloSituacaoPadraoView(PermissaoImportarSituacaoPadraoMixin, View):
    def get(self, request):
        resposta = HttpResponse(
            gerar_modelo_situacao_padrao(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resposta["Content-Disposition"] = 'attachment; filename="modelo_situacao_padrao.xlsx"'
        return resposta


class ImportarSituacaoPadraoView(PermissaoImportarSituacaoPadraoMixin, View):
    template_name = "importacoes/situacao_padrao.html"

    def get(self, request):
        request.session.pop(CHAVE_SESSAO_SITUACAO_PADRAO, None)
        return render(
            request,
            self.template_name,
            {
                "form": ImportarSituacaoPadraoForm(usuario=request.user),
                "importacoes": _importacoes_situacao_padrao(),
            },
        )

    def post(self, request):
        if request.POST.get("acao") == "aplicar":
            return self._aplicar(request)
        return self._prever(request)

    def _prever(self, request):
        form = ImportarSituacaoPadraoForm(request.POST, request.FILES, usuario=request.user)
        if not form.is_valid():
            return self._render_result(request, {"form": form})
        contrato = form.cleaned_data["contrato"]
        data_importacao = timezone.localdate()
        perfil_modelo = PerfilContrato.perfil_vigente(contrato, data_importacao)
        if perfil_modelo is None:
            form.add_error("contrato", "O contrato não tem perfil vigente para a data de hoje.")
            return self._render_result(request, {"form": form})
        try:
            arquivo = form.cleaned_data["arquivo"]
            previa = gerar_previa_situacao_padrao(
                arquivo,
                nome_arquivo=arquivo.name,
                contrato_id=contrato.pk,
                perfil_id=perfil_modelo.pk,
                perfil=perfil_de_dict(perfil_modelo.definicao),
                documentos_existentes=_dados_existentes_situacao_padrao(contrato),
                data_importacao=data_importacao,
            )
        except (ErroFormatoSituacaoPadrao, ErroPerfil, ValueError) as erro:
            return self._render_result(request, {"form": form, "erro": str(erro)})

        request.session[CHAVE_SESSAO_SITUACAO_PADRAO] = {
            "usuario_id": request.user.pk,
            "previa": _serializar_previa_situacao_padrao(previa),
        }
        return self._render_result(
            request,
            {
                "form": form,
                "previa": previa,
                "importacoes": _importacoes_situacao_padrao(),
            },
        )

    def _render_result(self, request, context):
        template = self.template_name
        if request.headers.get("HX-Request") == "true":
            template = "importacoes/_resultado_situacao_padrao.html"
        return render(request, template, context)

    def _aplicar(self, request):
        dados = request.session.get(CHAVE_SESSAO_SITUACAO_PADRAO)
        if not dados or dados.get("usuario_id") != request.user.pk:
            messages.error(request, "A prévia expirou. Envie o arquivo novamente.")
            return redirect("importar_situacao_padrao")
        try:
            previa = _previsao_situacao_padrao_da_sessao(dados["previa"])
            contrato = get_object_or_404(Contrato, pk=previa.contrato_id)
            if not _usuario_pode_importar_situacao_padrao(request.user, contrato):
                raise PermissionDenied
            perfil_modelo = get_object_or_404(
                PerfilContrato,
                pk=previa.perfil_id,
                contrato=contrato,
            )
            vigente = PerfilContrato.perfil_vigente(contrato, previa.data_importacao)
            if vigente is None or vigente.pk != perfil_modelo.pk:
                raise ValueError("O perfil vigente mudou. Envie o arquivo e gere outra prévia.")
            importacao = aplicar_previa_situacao_padrao(
                previa,
                contrato=contrato,
                perfil_modelo=perfil_modelo,
                usuario=request.user,
            )
        except PermissionDenied:
            raise
        except (ValueError, KeyError, TypeError) as erro:
            messages.error(request, str(erro))
            return redirect("importar_situacao_padrao")

        request.session.pop(CHAVE_SESSAO_SITUACAO_PADRAO, None)
        messages.success(
            request,
            f"Planilha {previa.arquivo_nome} aplicada: {previa.linhas_validas} linhas válidas, "
            f"{previa.linhas_invalidas} inválidas e {previa.mudancas_situacao} mudanças de situação.",
        )
        return redirect("importar_situacao_padrao")


def _usuario_pode_importar_situacao_padrao(usuario, contrato):
    return usuario.is_staff or Participacao.objects.filter(
        usuario=usuario,
        contrato=contrato,
        ativo=True,
        papel__in=(Usuario.Perfil.ADMIN, Usuario.Perfil.EQUIPE),
    ).exists()


def _dados_existentes_situacao_padrao(contrato):
    resultado = {}
    documentos = Documento.objects.filter(contrato=contrato).prefetch_related("emissoes__analises")
    for documento in documentos:
        emissoes = []
        for emissao in documento.emissoes.all():
            emissoes.append(
                {
                    "id": emissao.pk,
                    "revisao": emissao.revisao,
                    "versao": emissao.versao,
                    "fase": emissao.fase,
                    "data_emissao": emissao.data_emissao.isoformat(),
                    "analises": [
                        {
                            "id": analise.pk,
                            "situacao": analise.situacao,
                            "data_analise": analise.data_analise.isoformat() if analise.data_analise else None,
                            "observacao": analise.observacao,
                            "registrado_em": analise.registrado_em.isoformat(),
                        }
                        for analise in emissao.analises.all()
                    ],
                }
            )
        resultado[documento.identificador_base] = {"id": documento.pk, "emissoes": emissoes}
    return resultado


def _serializar_previa_situacao_padrao(previa):
    return {
        "contrato_id": previa.contrato_id,
        "perfil_id": previa.perfil_id,
        "data_importacao": previa.data_importacao.isoformat(),
        "arquivo_nome": previa.arquivo_nome,
        "cabecalhos": list(previa.cabecalhos),
        "documentos_encontrados": previa.documentos_encontrados,
        "documentos_nao_encontrados": previa.documentos_nao_encontrados,
        "codigos_invalidos": previa.codigos_invalidos,
        "situacoes_invalidas": previa.situacoes_invalidas,
        "linhas": [
            {
                **linha.__dict__,
                "data_analise": linha.data_analise.isoformat() if linha.data_analise else None,
                "campos_ignorados": [campo.__dict__ for campo in linha.campos_ignorados],
            }
            for linha in previa.linhas
        ],
    }


def _previsao_situacao_padrao_da_sessao(dados):
    from datetime import date

    linhas = []
    for item in dados["linhas"]:
        linha = dict(item)
        linha["data_analise"] = date.fromisoformat(linha["data_analise"]) if linha["data_analise"] else None
        linha["campos_ignorados"] = tuple(CampoIgnorado(**campo) for campo in linha["campos_ignorados"])
        linhas.append(LinhaSituacaoPadrao(**linha))
    return PreviaSituacaoPadrao(
        contrato_id=dados["contrato_id"],
        perfil_id=dados["perfil_id"],
        data_importacao=date.fromisoformat(dados["data_importacao"]),
        arquivo_nome=dados["arquivo_nome"],
        cabecalhos=tuple(dados["cabecalhos"]),
        linhas=tuple(linhas),
        documentos_encontrados=dados["documentos_encontrados"],
        documentos_nao_encontrados=dados["documentos_nao_encontrados"],
        codigos_invalidos=dados["codigos_invalidos"],
        situacoes_invalidas=dados["situacoes_invalidas"],
    )


def _importacoes_situacao_padrao():
    return ImportacaoSituacao.objects.filter(
        arquivo_nome__startswith=PREFIXO_ARQUIVO_SITUACAO_PADRAO
    ).select_related("contrato", "importado_por")[:20]


class ImportarCronogramaView(LoginRequiredMixin, UserPassesTestMixin, View):
    template_name = "importacoes/cronograma.html"
    raise_exception = True

    def test_func(self):
        return self.request.user.is_staff

    def get(self, request):
        request.session.pop(CHAVE_SESSAO_CRONOGRAMA, None)
        return render(
            request,
            self.template_name,
            {
                "form": ImportarCronogramaForm(),
                "importacoes": ImportacaoCronograma.objects.select_related(
                    "contrato", "importado_por"
                )[:20],
            },
        )

    def post(self, request):
        if request.POST.get("acao") == "confirmar":
            return self._confirmar(request)
        return self._prever(request)

    def _prever(self, request):
        form = ImportarCronogramaForm(request.POST, request.FILES)
        if not form.is_valid():
            return self._render_result(request, {"form": form})
        contrato = form.cleaned_data["contrato"]
        perfil_modelo = PerfilContrato.perfil_vigente(contrato, timezone.localdate())
        if perfil_modelo is None:
            form.add_error("contrato", "O contrato não tem perfil vigente para a data de hoje.")
            return self._render_result(request, {"form": form})
        try:
            arquivo = form.cleaned_data["arquivo"]
            documentos_previstos = ItemPrevisto.objects.filter(
                indice__contrato=contrato,
                indice__vigente=True,
                excluido=False,
            ).values_list("documento__identificador_base", flat=True).distinct()
            previa = gerar_previa_cronograma(
                arquivo,
                nome_arquivo=arquivo.name,
                contrato_id=contrato.pk,
                perfil_id=perfil_modelo.pk,
                perfil=perfil_de_dict(perfil_modelo.definicao),
                documentos_previstos=documentos_previstos,
            )
        except (ErroFormatoCronograma, ErroPerfil, ValueError) as erro:
            return self._render_result(request, {"form": form, "erro": str(erro)})

        request.session[CHAVE_SESSAO_CRONOGRAMA] = {
            "usuario_id": request.user.pk,
            "previa": _serializar_previa_cronograma(previa),
        }
        return self._render_result(request, {"form": form, "previa": previa})

    def _render_result(self, request, context):
        template = self.template_name
        if request.headers.get("HX-Request") == "true":
            template = "importacoes/_resultado_cronograma.html"
        return render(request, template, context)

    def _confirmar(self, request):
        dados = request.session.get(CHAVE_SESSAO_CRONOGRAMA)
        if not dados or dados.get("usuario_id") != request.user.pk:
            messages.error(request, "A prévia expirou. Envie o arquivo novamente.")
            return redirect("importar_cronograma")
        try:
            previa = _previsao_cronograma_da_sessao(dados["previa"])
            contrato = get_object_or_404(Contrato, pk=previa.contrato_id)
            perfil_modelo = get_object_or_404(
                PerfilContrato,
                pk=previa.perfil_id,
                contrato=contrato,
            )
            vigente = PerfilContrato.perfil_vigente(contrato, timezone.localdate())
            if vigente is None or vigente.pk != perfil_modelo.pk:
                raise ErroAplicacaoCronograma(
                    "O perfil vigente mudou. Envie o arquivo e gere outra prévia."
                )
            importacao = aplicar_previa_cronograma(
                previa,
                contrato=contrato,
                perfil_modelo=perfil_modelo,
                usuario=request.user,
            )
        except (ErroAplicacaoCronograma, ValueError, KeyError, TypeError) as erro:
            messages.error(request, str(erro))
            return redirect("importar_cronograma")
        request.session.pop(CHAVE_SESSAO_CRONOGRAMA, None)
        messages.success(
            request,
            f"Cronograma importado: {importacao.linhas_validas} previsões atualizadas e "
            f"{importacao.linhas_recusadas} linhas recusadas.",
        )
        return redirect("importar_cronograma")


def _serializar_previa_cronograma(previa):
    return {
        "contrato_id": previa.contrato_id,
        "perfil_id": previa.perfil_id,
        "arquivo_nome": previa.arquivo_nome,
        "linhas": [
            {
                "numero_linha": linha.numero_linha,
                "codigo": linha.codigo,
                "identificador_base": linha.identificador_base,
                "data_prevista": linha.data_prevista.isoformat() if linha.data_prevista else None,
                "categoria": linha.categoria,
                "mensagem": linha.mensagem,
            }
            for linha in previa.linhas
        ],
    }


def _previsao_cronograma_da_sessao(dados):
    from datetime import date

    return PreviaCronograma(
        contrato_id=dados["contrato_id"],
        perfil_id=dados["perfil_id"],
        arquivo_nome=dados["arquivo_nome"],
        linhas=tuple(
            LinhaCronograma(
                numero_linha=linha["numero_linha"],
                codigo=linha["codigo"],
                identificador_base=linha["identificador_base"],
                data_prevista=date.fromisoformat(linha["data_prevista"])
                if linha["data_prevista"]
                else None,
                categoria=linha["categoria"],
                mensagem=linha["mensagem"],
            )
            for linha in dados["linhas"]
        ),
    )
