from copy import deepcopy
from datetime import date
import os
import re
import tempfile
from pathlib import Path

from django import forms
from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from simple_history.admin import SimpleHistoryAdmin

from core.perfil import (
    ErroPerfil,
    Separador,
    feriados_nacionais,
    ler_feriados_extras,
    perfil_de_dict,
)
from core.perfil.feriados import feriados_acervo_detalhados
from core.perfil.codigo import ErroCodigo, interpretar, montar

from .forms import ImportarFeriadosForm
from .models import Contrato, FeriadoAcervo, Participacao, PerfilContrato


def _pode_gerenciar_acervo_feriados(usuario):
    return bool(usuario.is_active and (usuario.is_superuser or usuario.is_staff))


class PerfilContratoInline(admin.TabularInline):
    model = PerfilContrato
    extra = 0
    show_change_link = True


class ContratoAdminForm(forms.ModelForm):
    pin_painel = forms.CharField(
        label="PIN do painel",
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Informe de 4 a 6 dígitos. Deixe em branco para manter o PIN atual.",
    )

    class Meta:
        model = Contrato
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pin_painel_atual = self.instance.pin_painel
        self.fields["pin_painel"].initial = ""
        self.initial["pin_painel"] = ""

    def clean_pin_painel(self):
        pin = self.cleaned_data.get("pin_painel", "")
        if pin and not re.fullmatch(r"\d{4,6}", pin):
            raise ValidationError("O PIN deve ter de 4 a 6 dígitos.")
        return pin

    def save(self, commit=True):
        contrato = super().save(commit=False)
        pin = self.cleaned_data.get("pin_painel", "")
        if pin:
            contrato.definir_pin_painel(pin)
        else:
            contrato.pin_painel = self._pin_painel_atual
        if commit:
            contrato.save()
            self.save_m2m()
        return contrato


@admin.register(Contrato)
class ContratoAdmin(admin.ModelAdmin):
    form = ContratoAdminForm
    list_display = ("nome", "codigo_interno", "cliente", "ativo", "criado_em")
    list_filter = ("ativo", "cliente")
    search_fields = ("nome", "codigo_interno", "cliente", "descricao")
    inlines = (PerfilContratoInline,)
    readonly_fields = ("criado_em",)


@admin.register(FeriadoAcervo)
class FeriadoAcervoAdmin(SimpleHistoryAdmin):
    list_display = (
        "nome",
        "abrangencia",
        "uf",
        "municipio",
        "regra_resumida",
        "vigencia_de",
        "vigencia_ate",
    )
    list_filter = ("abrangencia", "uf", "tipo_regra")
    search_fields = ("nome", "uf", "municipio")

    def has_module_permission(self, request):
        return _pode_gerenciar_acervo_feriados(request.user)

    def has_view_permission(self, request, obj=None):
        return _pode_gerenciar_acervo_feriados(request.user)

    def has_add_permission(self, request):
        return _pode_gerenciar_acervo_feriados(request.user)

    def has_change_permission(self, request, obj=None):
        return _pode_gerenciar_acervo_feriados(request.user)

    def has_delete_permission(self, request, obj=None):
        return _pode_gerenciar_acervo_feriados(request.user)

    @admin.display(description="Regra")
    def regra_resumida(self, obj):
        if obj.tipo_regra == FeriadoAcervo.TipoRegra.FIXA:
            return f"{obj.dia:02d}/{obj.mes:02d}"
        return f"Páscoa {obj.deslocamento_pascoa:+d} dias"


@admin.register(PerfilContrato)
class PerfilContratoAdmin(admin.ModelAdmin):
    list_display = ("contrato", "versao", "vigencia_inicio", "ativo", "criado_em")
    list_filter = ("ativo", "contrato")
    search_fields = ("contrato__nome", "contrato__codigo_interno")
    fields = (
        "contrato",
        "versao",
        "vigencia_inicio",
        "definicao",
        "ativo",
        "caixas_codigo",
        "separadores_codigo",
        "exemplo_codigo",
        "link_testar_codigos",
        "link_feriados",
        "criado_em",
    )
    readonly_fields = (
        "caixas_codigo",
        "separadores_codigo",
        "exemplo_codigo",
        "link_testar_codigos",
        "link_feriados",
        "criado_em",
    )

    def get_urls(self):
        urls = [
            path(
                "<path:object_id>/feriados/",
                self.admin_site.admin_view(self.feriados),
                name="contratos_perfilcontrato_feriados",
            ),
            path(
                "<path:object_id>/importar-feriados/",
                self.admin_site.admin_view(self.importar_feriados),
                name="contratos_perfilcontrato_importar_feriados",
            ),
            path(
                "<path:object_id>/testar-codigos/",
                self.admin_site.admin_view(self.testar_codigos),
                name="contratos_perfilcontrato_testar_codigos",
            ),
        ]
        return urls + super().get_urls()

    @admin.display(description="Caixas do código")
    def caixas_codigo(self, obj):
        perfil, erro = self._perfil(obj)
        if erro:
            return format_html("<p>{}</p>", erro)
        linhas = (
            (
                segmento.nome,
                segmento.rotulo,
                segmento.padrao_regex,
                len(segmento.valores) if segmento.valores is not None else "Definidos pelo padrão",
                "Sim"
                if perfil.codigo.revisao_no_codigo
                and perfil.codigo.segmento_revisao == segmento.nome
                else "Não",
            )
            for segmento in perfil.codigo.campos
        )
        cabecalhos = ("Nome", "Rótulo", "Padrão", "Valores válidos", "Caixa da revisão")
        return format_html(
            '<table class="adminlist"><thead><tr>{}</tr></thead><tbody>{}</tbody></table>',
            format_html_join("", "<th>{}</th>", ((valor,) for valor in cabecalhos)),
            format_html_join(
                "",
                "<tr><td>{}</td><td>{}</td><td><code>{}</code></td><td>{}</td><td>{}</td></tr>",
                linhas,
            ),
        )

    @admin.display(description="Separadores")
    def separadores_codigo(self, obj):
        perfil, erro = self._perfil(obj)
        if erro:
            return format_html("<p>{}</p>", erro)
        separadores = [
            parte.texto
            for parte in perfil.codigo.segmentos
            if isinstance(parte, Separador)
        ]
        if not separadores:
            return "Nenhum separador"
        return format_html_join(" ", "<code>{}</code>", ((item,) for item in separadores))

    @admin.display(description="Exemplo de código")
    def exemplo_codigo(self, obj):
        perfil, erro = self._perfil(obj)
        if erro:
            return format_html("<p>{}</p>", erro)
        try:
            segmentos = {
                definicao.nome: self._valor_de_exemplo(definicao)
                for definicao in perfil.codigo.campos
            }
            codigo = montar(perfil, segmentos)
        except (ErroPerfil, ValueError) as erro:
            return format_html("<p>Não foi possível montar um exemplo: {}</p>", str(erro))
        return format_html("<code>{}</code>", codigo)

    @admin.display(description="Teste de códigos")
    def link_testar_codigos(self, obj):
        if not obj or not obj.pk:
            return "Salve o perfil para testar códigos."
        url = reverse("admin:contratos_perfilcontrato_testar_codigos", args=(obj.pk,))
        return format_html('<a class="button" href="{}">Testar códigos</a>', url)

    @admin.display(description="Feriados do perfil")
    def link_feriados(self, obj):
        if not obj or not obj.pk:
            return "Salve o perfil para consultar os feriados."
        url = reverse("admin:contratos_perfilcontrato_feriados", args=(obj.pk,))
        return format_html('<a class="button" href="{}">Feriados</a>', url)

    def feriados(self, request, object_id):
        perfil_db = get_object_or_404(PerfilContrato, pk=object_id)
        if not self.has_view_permission(request, perfil_db):
            raise PermissionDenied
        try:
            perfil = perfil_de_dict(perfil_db.definicao)
        except ErroPerfil as erro:
            raise Http404(f"O perfil salvo não é válido: {erro}") from erro

        ano_atual = timezone.localdate().year
        anos = (ano_atual, ano_atual + 1)
        itens = []
        sem_prazos = perfil.prazos is None
        if perfil.prazos:
            if perfil.prazos.feriados.nacionais:
                for ano in anos:
                    itens.extend(
                        {
                            "data": data,
                            "nome": "Feriado nacional obrigatório",
                            "origem": "Nacional (calculado)",
                        }
                        for data in feriados_nacionais(ano)
                    )
            itens.extend(
                {
                    "data": feriado.data,
                    "nome": feriado.nome,
                    "origem": "Extra do perfil",
                }
                for feriado in perfil.prazos.feriados.extras
                if feriado.data.year in anos
            )
            regiao = perfil.prazos.feriados.regiao
            if regiao is not None:
                regras_acervo = FeriadoAcervo.objects.filter(uf__iexact=regiao.uf).values(
                    "nome",
                    "abrangencia",
                    "uf",
                    "municipio",
                    "tipo_regra",
                    "dia",
                    "mes",
                    "deslocamento_pascoa",
                    "vigencia_de",
                    "vigencia_ate",
                )
                for ano in anos:
                    itens.extend(
                        {
                            "data": feriado.data,
                            "nome": feriado.nome,
                            "origem": f"Acervo ({feriado.uf})",
                        }
                        for feriado in feriados_acervo_detalhados(
                            ano,
                            regras_acervo,
                            uf=regiao.uf,
                            municipio=regiao.municipio,
                        )
                    )
        itens.sort(key=lambda item: (item["data"], item["origem"], item["nome"]))
        contexto = self._contexto_feriados(request, perfil_db)
        contexto.update(
            {
                "title": f"Feriados — {perfil_db}",
                "itens": itens,
                "anos": anos,
                "sem_prazos": sem_prazos,
                "url_importar": reverse(
                    "admin:contratos_perfilcontrato_importar_feriados",
                    args=(perfil_db.pk,),
                ),
            }
        )
        return TemplateResponse(
            request,
            "admin/contratos/perfilcontrato/feriados.html",
            contexto,
        )

    def importar_feriados(self, request, object_id):
        perfil_db = get_object_or_404(PerfilContrato, pk=object_id)
        if not self.has_change_permission(request, perfil_db):
            raise PermissionDenied
        try:
            perfil = perfil_de_dict(perfil_db.definicao)
        except ErroPerfil as erro:
            raise Http404(f"O perfil salvo não é válido: {erro}") from erro

        contexto = self._contexto_feriados(request, perfil_db)
        contexto.update(
            {
                "title": f"Importar feriados extras — {perfil_db}",
                "sem_prazos": perfil.prazos is None,
                "feriados_url": reverse(
                    "admin:contratos_perfilcontrato_feriados", args=(perfil_db.pk,)
                ),
                "change_url": reverse(
                    "admin:contratos_perfilcontrato_change", args=(perfil_db.pk,)
                ),
            }
        )
        if perfil.prazos is None:
            return TemplateResponse(
                request,
                "admin/contratos/perfilcontrato/importar_feriados.html",
                contexto,
            )

        chave_sessao = f"feriados_extras_preview_{perfil_db.pk}"
        if request.method == "POST" and "confirmar" in request.POST:
            previa = request.session.get(chave_sessao)
            if not previa or not previa.get("pode_confirmar"):
                messages.error(request, "Faça uma nova prévia antes de confirmar a importação.")
                contexto.update(
                    {
                        "form": ImportarFeriadosForm(),
                        "previa": request.session.get(chave_sessao),
                    }
                )
                return self._render_importacao_feriados(request, contexto)
            novo_perfil = self._criar_versao_com_feriados(perfil_db, previa["feriados"])
            request.session.pop(chave_sessao, None)
            messages.success(request, f"Feriados importados no perfil v{novo_perfil.versao}.")
            return self._redirecionar_feriados(novo_perfil)

        form = ImportarFeriadosForm(request.POST or None, request.FILES or None)
        previa = None
        if request.method == "POST" and form.is_valid():
            resultado = self._ler_arquivo_feriados(form.cleaned_data["arquivo"])
            datas_existentes = {feriado.data for feriado in perfil.prazos.feriados.extras}
            vistas = set(datas_existentes)
            para_adicionar = []
            duplicatas = []
            for feriado in resultado.feriados:
                if feriado.data in vistas:
                    motivo = (
                        "Data já cadastrada no perfil."
                        if feriado.data in datas_existentes
                        else "Data repetida na planilha."
                    )
                    duplicatas.append(
                        {
                            "data": feriado.data.isoformat(),
                            "nome": feriado.nome,
                            "motivo": motivo,
                        }
                    )
                    continue
                vistas.add(feriado.data)
                para_adicionar.append(
                    {"data": feriado.data.isoformat(), "nome": feriado.nome}
                )
            previa = {
                "feriados": para_adicionar,
                "validos": [
                    {"data": item.data.isoformat(), "nome": item.nome}
                    for item in resultado.feriados
                ],
                "duplicatas": duplicatas,
                "erros": [
                    {"linha": erro.linha, "mensagem": erro.mensagem}
                    for erro in resultado.erros
                ],
                "pode_confirmar": bool(resultado.feriados),
            }
            request.session[chave_sessao] = previa
        elif request.method == "POST":
            request.session.pop(chave_sessao, None)

        if previa is None:
            previa = request.session.get(chave_sessao)
        contexto.update({"form": form, "previa": previa})
        return self._render_importacao_feriados(request, contexto)

    def _render_importacao_feriados(self, request, contexto):
        return TemplateResponse(
            request,
            "admin/contratos/perfilcontrato/importar_feriados.html",
            contexto,
        )

    def _contexto_feriados(self, request, perfil_db):
        return {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "original": perfil_db,
            "change_url": reverse(
                "admin:contratos_perfilcontrato_change", args=(perfil_db.pk,)
            ),
        }

    @staticmethod
    def _ler_arquivo_feriados(arquivo):
        sufixo = Path(arquivo.name).suffix
        descritor, nome_temporario = tempfile.mkstemp(
            suffix=sufixo, dir=Path(__file__).resolve().parent
        )
        caminho = Path(nome_temporario)
        try:
            with os.fdopen(descritor, "wb") as destino:
                for trecho in arquivo.chunks():
                    destino.write(trecho)
            return ler_feriados_extras(caminho)
        finally:
            caminho.unlink(missing_ok=True)

    @staticmethod
    def _criar_versao_com_feriados(perfil_db, novos_feriados):
        definicao = deepcopy(perfil_db.definicao)
        prazos = definicao.setdefault("prazos", {})
        feriados = prazos.setdefault("feriados", {"nacionais": True, "extras": []})
        extras_existentes = feriados.setdefault("extras", [])
        datas_existentes = set()
        extras = []
        for item in extras_existentes:
            try:
                data_existente = date.fromisoformat(str(item["data"])[:10])
            except (KeyError, TypeError, ValueError):
                continue
            if data_existente in datas_existentes:
                continue
            datas_existentes.add(data_existente)
            extras.append(item)
        feriados["extras"] = extras
        for item in novos_feriados:
            data = date.fromisoformat(item["data"])
            if data in datas_existentes:
                continue
            extras.append({"data": data.isoformat(), "nome": item["nome"]})
            datas_existentes.add(data)

        hoje = timezone.localdate()
        definicao["vigencia_inicio"] = hoje.isoformat()
        proxima_versao = (
            PerfilContrato.objects.filter(contrato=perfil_db.contrato)
            .order_by("-versao")
            .values_list("versao", flat=True)
            .first()
            or 0
        ) + 1
        novo_perfil = PerfilContrato(
            contrato=perfil_db.contrato,
            versao=proxima_versao,
            vigencia_inicio=hoje,
            definicao=definicao,
            ativo=perfil_db.ativo,
        )
        novo_perfil.full_clean()
        novo_perfil.save()
        return novo_perfil

    @staticmethod
    def _redirecionar_feriados(perfil_db):
        return HttpResponseRedirect(
            reverse("admin:contratos_perfilcontrato_feriados", args=(perfil_db.pk,))
        )

    def testar_codigos(self, request, object_id):
        perfil_db = get_object_or_404(PerfilContrato, pk=object_id)
        if not self.has_view_permission(request, perfil_db):
            raise PermissionDenied
        try:
            perfil = perfil_de_dict(perfil_db.definicao)
        except ErroPerfil as erro:
            raise Http404(f"O perfil salvo não é válido: {erro}") from erro

        texto_codigos = request.POST.get("codigos", "") if request.method == "POST" else ""
        resultados = []
        if request.method == "POST":
            rotulos = {segmento.nome: segmento.rotulo for segmento in perfil.codigo.campos}
            for numero, codigo in enumerate(texto_codigos.splitlines(), start=1):
                if not codigo.strip():
                    continue
                resultado = interpretar(perfil, codigo)
                if isinstance(resultado, ErroCodigo):
                    resultados.append(
                        {
                            "linha": numero,
                            "codigo": codigo,
                            "valido": False,
                            "segmento": rotulos.get(resultado.segmento, resultado.segmento),
                            "mensagem": resultado.mensagem,
                            "caixas": (),
                        }
                    )
                else:
                    resultados.append(
                        {
                            "linha": numero,
                            "codigo": codigo,
                            "valido": True,
                            "segmento": "",
                            "mensagem": "Código válido.",
                            "caixas": tuple(
                                (
                                    segmento.nome,
                                    segmento.rotulo,
                                    resultado.segmentos[segmento.nome],
                                    resultado.significados.get(segmento.nome, ""),
                                )
                                for segmento in perfil.codigo.campos
                                if segmento.nome in resultado.segmentos
                            ),
                        }
                    )

        contexto = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "original": perfil_db,
            "title": f"Testar códigos — {perfil_db}",
            "texto_codigos": texto_codigos,
            "resultados": resultados,
            "change_url": reverse(
                "admin:contratos_perfilcontrato_change", args=(perfil_db.pk,)
            ),
        }
        return TemplateResponse(
            request,
            "admin/contratos/perfilcontrato/testar_codigos.html",
            contexto,
        )

    @staticmethod
    def _perfil(obj):
        try:
            return perfil_de_dict(obj.definicao), None
        except ErroPerfil as erro:
            return None, str(erro)

    @staticmethod
    def _valor_de_exemplo(segmento):
        candidatos = list(segmento.valores or {})
        candidatos.extend(("0", "1", "A", "00", "01", "AA", "001", "000", "0000", "A1", "CC"))
        for candidato in candidatos:
            if re.fullmatch(segmento.padrao_regex, candidato, re.IGNORECASE):
                return candidato
        padrao = segmento.padrao_regex
        repeticao = re.fullmatch(r"\\d\{(\d+)\}", padrao)
        if repeticao:
            return "0" * int(repeticao.group(1))
        repeticao = re.fullmatch(r"\[A-Z\]\{(\d+)\}", padrao)
        if repeticao:
            return "A" * int(repeticao.group(1))
        raise ValueError(f"Não há valor de exemplo simples para o segmento '{segmento.nome}'.")


@admin.register(Participacao)
class ParticipacaoAdmin(admin.ModelAdmin):
    list_display = ("usuario", "contrato", "papel", "ativo")
    list_filter = ("papel", "ativo", "contrato")
    search_fields = ("usuario__username", "usuario__first_name", "usuario__last_name", "contrato__nome")
