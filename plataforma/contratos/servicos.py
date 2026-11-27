from django.db.models import Count, IntegerField, OuterRef, Prefetch, Subquery, Value
from django.db.models.functions import Coalesce, Lower
from django.utils import timezone

from documentos.models import Documento

from .models import Contrato, Participacao, PerfilContrato


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
