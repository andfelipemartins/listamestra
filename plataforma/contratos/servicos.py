import calendar
from datetime import date

from django.db import transaction
from django.db.models import Count, IntegerField, OuterRef, Prefetch, Subquery, Value
from django.db.models.functions import Coalesce, Lower
from django.utils import timezone
from django.utils.dateparse import parse_date

from core.perfil import ErroPerfil, perfil_de_dict
from core.perfil.feriados import feriados_acervo_detalhados
from core.perfil.feriados import feriados_nacionais
from documentos.models import Documento

from .models import (
    Contrato,
    DiaNaoUtilContrato,
    FeriadoAcervo,
    Participacao,
    PerfilContrato,
)


def listar_contratos():
    return [_resumo_contrato(contrato) for contrato in _contratos_com_resumo()]


def detalhe_contrato(contrato):
    consulta = _contratos_com_resumo().prefetch_related(
        Prefetch(
            "participacoes",
            queryset=Participacao.objects.select_related("usuario").order_by(
                "-ativo",
                "usuario__first_name",
                "usuario__last_name",
                "usuario__username",
                "pk",
            ),
            to_attr="participacoes_detalhe",
        )
    )
    contrato_carregado = consulta.get(pk=contrato.pk)
    resumo = _resumo_contrato(contrato_carregado)
    resumo["participantes"] = [
        {
            "nome": participacao.usuario.get_full_name() or participacao.usuario.username,
            "usuario": participacao.usuario.username,
            "papel": participacao.get_papel_display(),
            "ativo": participacao.ativo,
        }
        for participacao in contrato_carregado.participacoes_detalhe
    ]
    return resumo


def _contratos_com_resumo():
    hoje = timezone.localdate()
    perfis_vigentes = PerfilContrato.objects.filter(
        ativo=True,
        vigencia_inicio__lte=hoje,
    ).order_by("-vigencia_inicio", "-versao")
    consulta = Contrato.objects.prefetch_related(
        Prefetch("perfis", queryset=perfis_vigentes, to_attr="perfis_vigentes")
    )
    for papel, _ in Participacao._meta.get_field("papel").choices:
        participacoes_do_papel = (
            Participacao.objects.filter(
                contrato_id=OuterRef("pk"),
                ativo=True,
                papel=papel,
            )
            .order_by()
            .values("contrato_id")
            .annotate(total=Count("pk"))
            .values("total")[:1]
        )
        consulta = consulta.annotate(
            **{
                f"_participacoes_{papel}": Coalesce(
                    Subquery(participacoes_do_papel, output_field=IntegerField()),
                    Value(0),
                )
            }
        )
    documentos_em_conta = (
        Documento.objects.filter(
            contrato_id=OuterRef("pk"),
            cancelado_em__isnull=True,
        )
        .order_by()
        .values("contrato_id")
        .annotate(total=Count("pk"))
        .values("total")[:1]
    )
    return consulta.annotate(
        _documentos_em_conta=Coalesce(
            Subquery(documentos_em_conta, output_field=IntegerField()),
            Value(0),
        )
    ).order_by("-ativo", Lower("nome"), "pk")


def _resumo_contrato(contrato):
    perfil = next(iter(getattr(contrato, "perfis_vigentes", ())), None)
    definicao = perfil.definicao if perfil and isinstance(perfil.definicao, dict) else {}
    participacoes_por_papel = [
        {
            "papel": papel,
            "rotulo": Participacao(papel=papel).get_papel_display(),
            "quantidade": getattr(contrato, f"_participacoes_{papel}"),
        }
        for papel, _ in Participacao._meta.get_field("papel").choices
    ]
    return {
        "contrato": contrato,
        "codigo_interno": contrato.codigo_interno,
        "nome": contrato.nome,
        "cliente": contrato.cliente,
        "ativo": contrato.ativo,
        "nome_perfil": definicao.get("nome"),
        "participacoes_por_papel": participacoes_por_papel,
        "total_documentos_em_conta": contrato._documentos_em_conta,
    }


def regiao_do_perfil(perfil_db):
    definicao = perfil_db.definicao if perfil_db and isinstance(perfil_db.definicao, dict) else {}
    regiao = (
        definicao.get("prazos", {}).get("feriados", {}).get("regiao")
        if isinstance(definicao.get("prazos"), dict)
        else None
    )
    if not isinstance(regiao, dict):
        return {"uf": "", "municipio": ""}
    return {
        "uf": str(regiao.get("uf", "")).strip().upper(),
        "municipio": str(regiao.get("municipio", "")).strip(),
    }


def perfis_configuraveis(contrato):
    return list(PerfilContrato.objects.filter(contrato=contrato, ativo=True).order_by("versao"))


@transaction.atomic
def atualizar_regiao_contrato(contrato, uf, municipio):
    contrato.regiao_uf = (uf or "").strip().upper()
    contrato.regiao_municipio = (municipio or "").strip()
    contrato.save(update_fields=("regiao_uf", "regiao_municipio"))
    for perfil_db in perfis_configuraveis(contrato):
        definicao = dict(perfil_db.definicao)
        prazos = dict(definicao.get("prazos") or {})
        feriados = dict(prazos.get("feriados") or {"nacionais": True, "extras": []})
        if contrato.regiao_uf and contrato.regiao_municipio:
            feriados["regiao"] = {
                "uf": contrato.regiao_uf,
                "municipio": contrato.regiao_municipio,
            }
        else:
            feriados.pop("regiao", None)
        prazos["feriados"] = feriados
        definicao["prazos"] = prazos
        perfil_de_dict(definicao)
        perfil_db.definicao = definicao
        perfil_db.save(update_fields=("definicao",))


def carregar_escopos_contrato(contrato):
    hoje = timezone.localdate()
    perfil_db = PerfilContrato.perfil_vigente(contrato, hoje)
    if perfil_db is None:
        perfil_db = PerfilContrato.objects.filter(contrato=contrato, ativo=True).order_by(
            "-vigencia_inicio", "-versao"
        ).first()
    regras = []
    if perfil_db and isinstance(perfil_db.definicao, dict):
        regras = perfil_db.definicao.get("escopos") or []
    classes_padrao = {
        item.get("nome", "").casefold(): list(item.get("classes") or [])
        for item in regras
        if isinstance(item, dict) and "tipos" not in item
    }
    classes_por_tipo = {}
    for item in regras:
        if isinstance(item, dict) and "tipos" in item:
            classes_por_tipo.setdefault(item.get("nome", "").casefold(), []).append(item)
    return [
        {
            "escopo": escopo,
            "classes": list(escopo.classes or classes_padrao.get(escopo.nome.casefold(), [])),
            "regras_por_tipo": classes_por_tipo.get(escopo.nome.casefold(), []),
        }
        for escopo in contrato.escopos.order_by("nome", "pk")
    ]


@transaction.atomic
def materializar_escopos_do_perfil(contrato):
    perfil_db = PerfilContrato.objects.filter(contrato=contrato, ativo=True).order_by(
        "-vigencia_inicio", "-versao"
    ).first()
    if not perfil_db or not isinstance(perfil_db.definicao, dict):
        return
    for regra in perfil_db.definicao.get("escopos", []) or []:
        if not isinstance(regra, dict) or not str(regra.get("nome", "")).strip():
            continue
        nome = str(regra["nome"]).strip()
        Escopo = contrato.escopos.model
        Escopo.objects.get_or_create(
            contrato=contrato,
            nome__iexact=nome,
            defaults={
                "nome": nome,
                "classes": list(regra.get("classes") or [])
                if "tipos" not in regra
                else [],
            },
        )


@transaction.atomic
def sincronizar_escopos_contrato(contrato, *, nomes_anteriores=None):
    nomes_anteriores = nomes_anteriores or {}
    escopos = list(contrato.escopos.order_by("nome", "pk"))
    nomes = {escopo.nome.casefold(): escopo.nome for escopo in escopos}
    for perfil_db in perfis_configuraveis(contrato):
        definicao = dict(perfil_db.definicao)
        regras_anteriores = definicao.get("escopos") or []
        regras_tipo = []
        for regra in regras_anteriores:
            if not isinstance(regra, dict) or "tipos" not in regra:
                continue
            nome_atual = nomes_anteriores.get(regra.get("nome"), regra.get("nome"))
            novo_nome = nomes.get(str(nome_atual).casefold())
            if novo_nome:
                regras_tipo.append({**regra, "nome": novo_nome})
        regras = [
            {"nome": escopo.nome, "classes": list(escopo.classes)}
            for escopo in escopos
            if escopo.classes
        ]
        definicao["escopos"] = regras + regras_tipo
        perfil_de_dict(definicao)
        perfil_db.definicao = definicao
        perfil_db.save(update_fields=("definicao",))


def calendario_contrato(contrato, ano, mes):
    inicio = date(ano, mes, 1)
    fim = date(ano + (mes == 12), (mes % 12) + 1, 1)
    feriados = {}

    def incluir(data, nome, origem):
        feriados.setdefault(data, []).append({"nome": nome, "origem": origem})

    perfil_db = PerfilContrato.perfil_vigente(contrato, date(ano, mes, 1))
    definicao = perfil_db.definicao if perfil_db and isinstance(perfil_db.definicao, dict) else {}
    prazos = definicao.get("prazos", {}) if isinstance(definicao.get("prazos"), dict) else {}
    feriados_perfil = prazos.get("feriados", {}) if isinstance(prazos, dict) else {}
    if feriados_perfil.get("nacionais", True):
        for data in feriados_nacionais(ano):
            incluir(data, "Feriado nacional obrigatório", "Nacional")

    if contrato.regiao_uf and contrato.regiao_municipio:
        regras = list(
            FeriadoAcervo.objects.filter(uf__iexact=contrato.regiao_uf).values(
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
        )
        for feriado in feriados_acervo_detalhados(
            ano,
            regras,
            uf=contrato.regiao_uf,
            municipio=contrato.regiao_municipio,
        ):
            incluir(feriado.data, feriado.nome, f"Acervo ({feriado.uf})")

    extras = feriados_perfil.get("extras", [])
    for extra in extras:
        if isinstance(extra, dict):
            data = parse_date(str(extra.get("data", "")))
            if data and data.year == ano:
                incluir(data, str(extra.get("nome", "Feriado extra")), "Perfil")

    manuais = {
        dia.data: dia
        for dia in DiaNaoUtilContrato.objects.filter(
            contrato=contrato,
            data__gte=inicio,
            data__lt=fim,
        )
    }
    semanas = []
    for semana in calendar.Calendar(firstweekday=0).monthdatescalendar(ano, mes):
        celulas = []
        for data in semana:
            celulas.append(
                {
                    "data": data,
                    "no_mes": data.month == mes,
                    "hoje": data == timezone.localdate(),
                    "feriados": sorted(
                        feriados.get(data, []), key=lambda item: (item["origem"], item["nome"])
                    ),
                    "manual": manuais.get(data),
                }
            )
        semanas.append(celulas)
    meses = (
        "janeiro",
        "fevereiro",
        "março",
        "abril",
        "maio",
        "junho",
        "julho",
        "agosto",
        "setembro",
        "outubro",
        "novembro",
        "dezembro",
    )
    return {
        "ano": ano,
        "mes": mes,
        "titulo": f"{meses[mes - 1].capitalize()} de {ano}",
        "dias_semana": ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"),
        "semanas": semanas,
        "anterior": (ano - (mes == 1), 12 if mes == 1 else mes - 1),
        "proximo": (ano + (mes == 12), 1 if mes == 12 else mes + 1),
    }
