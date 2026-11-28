from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.urls import reverse
from django.utils import timezone
from simple_history.utils import update_change_reason

from contas.models import Usuario
from contratos.models import Participacao
from documentos.models import Emissao

from .models import Equipe, Tarefa


def eh_admin_contrato(usuario, contrato):
    return bool(
        usuario.is_staff
        or usuario.is_superuser
        or Participacao.objects.filter(
            usuario=usuario,
            contrato=contrato,
            papel=Usuario.Perfil.ADMIN,
            ativo=True,
        ).exists()
    )


def equipes_geridas(usuario, contrato):
    equipes = list(
        Equipe.objects.filter(contrato=contrato, gestor=usuario)
        .select_related("equipe_mae")
        .order_by("pk")
    )
    todas = list(Equipe.objects.filter(contrato=contrato).values_list("pk", "equipe_mae_id"))
    filhos = {}
    for equipe_id, mae_id in todas:
        filhos.setdefault(mae_id, []).append(equipe_id)
    ids = {equipe.pk for equipe in equipes}
    fila = list(ids)
    while fila:
        atual = fila.pop()
        for filho in filhos.get(atual, ()):
            if filho not in ids:
                ids.add(filho)
                fila.append(filho)
    return Equipe.objects.filter(pk__in=ids).order_by("nome", "pk")


def responsaveis_permitidos(usuario, contrato):
    participantes = Usuario.objects.filter(
        participacoes_contratuais__contrato=contrato,
        participacoes_contratuais__ativo=True,
        is_active=True,
    ).distinct()
    if eh_admin_contrato(usuario, contrato):
        if usuario.is_staff or usuario.is_superuser:
            participantes = participantes | Usuario.objects.filter(pk=usuario.pk)
        return participantes.distinct().order_by("first_name", "last_name", "username")
    equipe_ids = equipes_geridas(usuario, contrato).values_list("pk", flat=True)
    ids_membros = Equipe.objects.filter(pk__in=equipe_ids).values_list(
        "membros__pk", flat=True
    )
    if not participantes.filter(pk=usuario.pk).exists() and not usuario.is_staff:
        return Usuario.objects.none()
    return (participantes.filter(Q(pk=usuario.pk) | Q(pk__in=ids_membros))
            | Usuario.objects.filter(pk=usuario.pk, is_staff=True)).distinct().order_by(
        "first_name", "last_name", "username"
    )


def pode_atribuir(usuario, responsavel, contrato):
    if usuario.pk == responsavel.pk:
        return bool(
            usuario.is_staff
            or Participacao.objects.filter(
                usuario=usuario, contrato=contrato, ativo=True
            ).exists()
        )
    if eh_admin_contrato(usuario, contrato):
        return Participacao.objects.filter(
            usuario=responsavel, contrato=contrato, ativo=True
        ).exists()
    if not Participacao.objects.filter(
        usuario=responsavel, contrato=contrato, ativo=True
    ).exists():
        return False
    equipes_ids = equipes_geridas(usuario, contrato).values_list("pk", flat=True)
    return Equipe.objects.filter(pk__in=equipes_ids, membros=responsavel).exists()


def validar_atribuicao(usuario, responsavel, contrato):
    if not pode_atribuir(usuario, responsavel, contrato):
        raise PermissionDenied("Você não pode atribuir tarefas para esta pessoa neste contrato.")


def tarefas_visiveis(usuario, contrato):
    if eh_admin_contrato(usuario, contrato):
        return Tarefa.objects.filter(contrato=contrato)
    equipes_ids = equipes_geridas(usuario, contrato).values_list("pk", flat=True)
    return Tarefa.objects.filter(contrato=contrato).filter(
        Q(responsavel=usuario)
        | Q(criada_por=usuario)
        | Q(responsavel__equipes_tarefas__pk__in=equipes_ids)
    ).distinct()


def pode_ver_tarefa(usuario, tarefa):
    if eh_admin_contrato(usuario, tarefa.contrato):
        return True
    if tarefa.responsavel_id == usuario.pk or tarefa.criada_por_id == usuario.pk:
        return True
    equipes_ids = equipes_geridas(usuario, tarefa.contrato).values_list("pk", flat=True)
    return tarefa.responsavel.equipes_tarefas.filter(pk__in=equipes_ids).exists()


def pode_editar_tarefa(usuario, tarefa):
    if tarefa.status != Tarefa.Status.ABERTA:
        return False
    if eh_admin_contrato(usuario, tarefa.contrato):
        return True
    if tarefa.criada_por_id == usuario.pk or tarefa.responsavel_id == usuario.pk:
        return True
    return tarefa.responsavel.equipes_tarefas.filter(
        pk__in=equipes_geridas(usuario, tarefa.contrato).values_list("pk", flat=True)
    ).exists()


def pode_cancelar_tarefa(usuario, tarefa):
    if tarefa.status != Tarefa.Status.ABERTA:
        return False
    if eh_admin_contrato(usuario, tarefa.contrato):
        return True
    if tarefa.criada_por_id == usuario.pk and tarefa.responsavel_id == usuario.pk:
        return True
    return tarefa.responsavel.equipes_tarefas.filter(
        pk__in=equipes_geridas(usuario, tarefa.contrato).values_list("pk", flat=True)
    ).exists()


def pode_concluir_tarefa(usuario, tarefa):
    return tarefa.status == Tarefa.Status.ABERTA and tarefa.responsavel_id == usuario.pk


@transaction.atomic
def criar_tarefa(*, contrato, usuario, titulo, descricao, responsavel, prazo, documento=None):
    validar_atribuicao(usuario, responsavel, contrato)
    tarefa = Tarefa(
        contrato=contrato,
        titulo=titulo.strip(),
        descricao=descricao,
        responsavel=responsavel,
        criada_por=usuario,
        prazo=prazo,
        documento=documento,
    )
    tarefa._history_user = usuario
    tarefa.full_clean()
    tarefa.save()
    update_change_reason(tarefa, "Tarefa criada")
    return tarefa


@transaction.atomic
def editar_tarefa(*, tarefa, usuario, titulo, descricao, responsavel, prazo, documento=None):
    if not pode_editar_tarefa(usuario, tarefa):
        raise PermissionDenied("Você não pode editar esta tarefa.")
    validar_atribuicao(usuario, responsavel, tarefa.contrato)
    tarefa.titulo = titulo.strip()
    tarefa.descricao = descricao
    tarefa.responsavel = responsavel
    tarefa.prazo = prazo
    tarefa.documento = documento
    tarefa._history_user = usuario
    tarefa.full_clean()
    tarefa.save()
    update_change_reason(tarefa, "Tarefa alterada")
    return tarefa


@transaction.atomic
def concluir_tarefa(*, tarefa, usuario):
    if not pode_concluir_tarefa(usuario, tarefa):
        raise PermissionDenied("Somente o responsável pode concluir esta tarefa aberta.")
    tarefa.status = Tarefa.Status.CONCLUIDA
    tarefa.concluida_em = timezone.now()
    tarefa._history_user = usuario
    tarefa.full_clean()
    tarefa.save(update_fields=("status", "concluida_em"))
    update_change_reason(tarefa, "Tarefa concluída")
    return tarefa


@transaction.atomic
def cancelar_tarefa(*, tarefa, usuario):
    if not pode_cancelar_tarefa(usuario, tarefa):
        raise PermissionDenied("Você não pode cancelar esta tarefa.")
    tarefa.status = Tarefa.Status.CANCELADA
    tarefa._history_user = usuario
    tarefa.full_clean()
    tarefa.save(update_fields=("status",))
    update_change_reason(tarefa, "Tarefa cancelada")
    return tarefa


def tarefas_da_equipe(usuario, contrato):
    ids = equipes_geridas(usuario, contrato).values_list("pk", flat=True)
    return Tarefa.objects.filter(
        contrato=contrato, responsavel__equipes_tarefas__pk__in=ids
    ).distinct()


def consulta_tarefas_com_sugestao(queryset):
    emissao_nova = Emissao.objects.filter(
        documento_id=OuterRef("documento_id"), criado_em__gt=OuterRef("criada_em")
    )
    return queryset.annotate(_emissao_nova=Exists(emissao_nova))


def carregar_resumo_tarefas(usuario, contrato, *, hoje=None, limite=5):
    hoje = hoje or timezone.localdate()
    abertas = consulta_tarefas_com_sugestao(
        Tarefa.objects.filter(
            contrato=contrato, responsavel=usuario, status=Tarefa.Status.ABERTA
        ).select_related("documento", "responsavel")
    )
    total = abertas.count()
    ordenadas = abertas.order_by(
        models_case_atrasada(hoje), "prazo", "criada_em", "pk"
    )[:limite]
    equipes = equipes_geridas(usuario, contrato)
    equipe = None
    if equipes.exists():
        tarefas = tarefas_da_equipe(usuario, contrato).filter(status=Tarefa.Status.ABERTA)
        equipe = {
            "abertas": tarefas.count(),
            "atrasadas": tarefas.filter(prazo__lt=hoje).count(),
        }
    return {
        "tarefas_minhas": list(ordenadas),
        "tarefas_minhas_total": total,
        "tarefas_equipe_resumo": equipe,
        "tarefas_url": reverse("tarefas:lista"),
    }


def modelos_prazo(queryset, filtro, *, hoje=None):
    hoje = hoje or timezone.localdate()
    if filtro == "atrasadas":
        return queryset.filter(status=Tarefa.Status.ABERTA, prazo__lt=hoje)
    if filtro == "hoje":
        return queryset.filter(prazo=hoje)
    if filtro == "futuras":
        return queryset.filter(prazo__gt=hoje)
    if filtro == "sem_prazo":
        return queryset.filter(prazo__isnull=True)
    return queryset


def modelos_status(queryset, filtro):
    if filtro in Tarefa.Status.values:
        return queryset.filter(status=filtro)
    return queryset


def models_case_atrasada(hoje):
    from django.db.models import Case, IntegerField, When

    return Case(
        When(status=Tarefa.Status.ABERTA, prazo__lt=hoje, then=0),
        default=1,
        output_field=IntegerField(),
    )
