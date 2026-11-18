import re

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join
import re

from core.perfil import ErroPerfil, Separador, perfil_de_dict
from core.perfil.codigo import ErroCodigo, interpretar, montar

from .models import Contrato, Participacao, PerfilContrato


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
        "criado_em",
    )
    readonly_fields = (
        "caixas_codigo",
        "separadores_codigo",
        "exemplo_codigo",
        "link_testar_codigos",
        "criado_em",
    )

    def get_urls(self):
        urls = [
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
