from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from contas.models import Usuario

from .forms import (
    ContratoDadosForm,
    DiaNaoUtilForm,
    EscopoContratoForm,
    ParticipacaoEdicaoForm,
    ParticipacaoForm,
)
from .models import (
    Contrato,
    DiaNaoUtilContrato,
    EscopoContrato,
    Participacao,
    PerfilContrato,
)
from .servicos import (
    atualizar_regiao_contrato,
    calendario_contrato,
    carregar_escopos_contrato,
    detalhe_contrato,
    listar_contratos,
    materializar_escopos_do_perfil,
    regiao_do_perfil,
    sincronizar_escopos_contrato,
)


@login_required
def contratos_lista(request):
    if not request.user.is_staff and not request.user.is_superuser:
        raise PermissionDenied
    return render(
        request,
        "contratos/lista.html",
        {"contratos": listar_contratos()},
    )


@login_required
def contrato_detalhe(request, contrato_id):
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    participacao_atual = Participacao.objects.filter(
        contrato=contrato,
        usuario=request.user,
        ativo=True,
    ).first()
    equipe_global = request.user.is_staff or request.user.is_superuser
    if not equipe_global and participacao_atual is None:
        raise PermissionDenied
    pode_editar = equipe_global or (
        participacao_atual is not None
        and participacao_atual.papel == Usuario.Perfil.ADMIN
    )
    formularios_invalidos = {}

    if pode_editar:
        materializar_escopos_do_perfil(contrato)

    if request.method == "POST":
        resultado = _processar_acao(request, contrato)
        if isinstance(resultado, tuple):
            acao, formulario = resultado
            formularios_invalidos[acao] = formulario
        elif resultado is not None:
            return resultado

    return _render_detalhe(
        request,
        contrato,
        pode_editar=pode_editar,
        formularios_invalidos=formularios_invalidos,
    )


def _processar_acao(request, contrato):
    acao = request.POST.get("acao", "")
    if acao == "dados":
        formulario = ContratoDadosForm(
            request.POST,
            instance=contrato,
            initial={
                "regiao_uf": contrato.regiao_uf,
                "regiao_municipio": contrato.regiao_municipio,
            },
        )
        if formulario.is_valid():
            with transaction.atomic():
                atualizado = formulario.save()
                atualizar_regiao_contrato(
                    atualizado,
                    formulario.cleaned_data["regiao_uf"],
                    formulario.cleaned_data["regiao_municipio"],
                )
            messages.success(request, "Dados do contrato atualizados.")
            return _redirecionar(contrato)
        return acao, formulario

    if acao == "adicionar_participante":
        formulario = ParticipacaoForm(request.POST)
        if formulario.is_valid():
            Participacao.objects.update_or_create(
                contrato=contrato,
                usuario=formulario.cleaned_data["usuario"],
                defaults={
                    "papel": formulario.cleaned_data["papel"],
                    "funcao": formulario.cleaned_data["funcao"].strip(),
                    "ativo": True,
                },
            )
            messages.success(request, "Participante atualizado no contrato.")
            return _redirecionar(contrato, "participantes")
        return acao, formulario

    if acao == "editar_participante":
        participacao = get_object_or_404(
            Participacao,
            contrato=contrato,
            pk=request.POST.get("participacao_id"),
        )
        formulario = ParticipacaoEdicaoForm(request.POST)
        if formulario.is_valid():
            participacao.papel = formulario.cleaned_data["papel"]
            participacao.funcao = formulario.cleaned_data["funcao"].strip()
            participacao.save(update_fields=("papel", "funcao"))
            messages.success(request, "Papel e função atualizados.")
            return _redirecionar(contrato, "participantes")
        return f"participante-{participacao.pk}", formulario

    if acao == "desativar_participante":
        participacao = get_object_or_404(
            Participacao,
            contrato=contrato,
            pk=request.POST.get("participacao_id"),
        )
        participacao.ativo = False
        participacao.save(update_fields=("ativo",))
        messages.success(request, "Participação desativada.")
        return _redirecionar(contrato, "participantes")

    if acao == "salvar_dia":
        formulario = DiaNaoUtilForm(request.POST)
        if formulario.is_valid():
            DiaNaoUtilContrato.objects.update_or_create(
                contrato=contrato,
                data=formulario.cleaned_data["data"],
                defaults={"descricao": formulario.cleaned_data["descricao"]},
            )
            messages.success(request, "Dia não útil registrado no calendário.")
            return _redirecionar_calendario(contrato, formulario.cleaned_data["data"])
        return acao, formulario

    if acao == "adicionar_escopo":
        formulario = EscopoContratoForm(request.POST)
        if formulario.is_valid():
            escopo = EscopoContrato(
                contrato=contrato,
                nome=formulario.cleaned_data["nome"],
                classes=formulario.cleaned_data["classes"],
            )
            try:
                with transaction.atomic():
                    escopo.full_clean()
                    escopo.save()
                    sincronizar_escopos_contrato(contrato)
            except (ValidationError, ValueError, IntegrityError) as erro:
                _adicionar_erro_formulario(formulario, erro)
                return acao, formulario
            messages.success(request, "Escopo cadastrado.")
            return _redirecionar(contrato, "escopos")
        return acao, formulario

    if acao == "editar_escopo":
        escopo = get_object_or_404(
            EscopoContrato,
            contrato=contrato,
            pk=request.POST.get("escopo_id"),
        )
        formulario = EscopoContratoForm(request.POST)
        if formulario.is_valid():
            nome_anterior = escopo.nome
            escopo.nome = formulario.cleaned_data["nome"]
            escopo.classes = formulario.cleaned_data["classes"]
            try:
                with transaction.atomic():
                    escopo.full_clean()
                    escopo.save()
                    sincronizar_escopos_contrato(
                        contrato,
                        nomes_anteriores={nome_anterior: escopo.nome},
                    )
            except (ValidationError, ValueError, IntegrityError) as erro:
                _adicionar_erro_formulario(formulario, erro)
                return f"escopo-{escopo.pk}", formulario
            messages.success(request, "Escopo atualizado.")
            return _redirecionar(contrato, "escopos")
        return f"escopo-{escopo.pk}", formulario

    if acao == "remover_escopo":
        escopo = get_object_or_404(
            EscopoContrato,
            contrato=contrato,
            pk=request.POST.get("escopo_id"),
        )
        with transaction.atomic():
            escopo.delete()
            sincronizar_escopos_contrato(contrato)
        messages.success(request, "Escopo removido do contrato.")
        return _redirecionar(contrato, "escopos")

    messages.error(request, "Ação inválida para o contrato.")
    return _redirecionar(contrato)


def _adicionar_erro_formulario(formulario, erro):
    if isinstance(erro, ValidationError):
        mensagens = erro.messages
    else:
        mensagens = [str(erro)]
    for mensagem in mensagens:
        formulario.add_error(None, mensagem)


def _render_detalhe(request, contrato, *, pode_editar, formularios_invalidos):
    hoje = timezone.localdate()
    try:
        ano = int(request.GET.get("ano", hoje.year))
        mes = int(request.GET.get("mes", hoje.month))
        if not 1 <= ano <= 9998 or not 1 <= mes <= 12:
            raise ValueError
    except (TypeError, ValueError):
        ano, mes = hoje.year, hoje.month
    try:
        selecionada = date.fromisoformat(request.GET.get("data", ""))
    except (TypeError, ValueError):
        selecionada = date(ano, mes, hoje.day if (ano, mes) == (hoje.year, hoje.month) else 1)
    if (selecionada.year, selecionada.month) != (ano, mes):
        selecionada = date(ano, mes, 1)

    participantes_db = (
        Participacao.objects.filter(contrato=contrato)
        .select_related("usuario")
        .order_by("-ativo", "usuario__first_name", "usuario__last_name", "usuario__username")
    )
    participantes = [
        {
            "participacao": item,
            "nome": item.usuario.get_full_name() or item.usuario.username,
            "usuario": item.usuario.username,
            "papel": item.get_papel_display(),
            "papel_valor": item.papel,
            "funcao": item.funcao,
            "ativo": item.ativo,
        }
        for item in participantes_db
    ]
    perfil_vigente = PerfilContrato.perfil_vigente(contrato, hoje)
    regiao = {"uf": contrato.regiao_uf, "municipio": contrato.regiao_municipio}
    if not regiao["uf"] and perfil_vigente:
        regiao = regiao_do_perfil(perfil_vigente)
    scopes = carregar_escopos_contrato(contrato)

    formulario_dados = formularios_invalidos.get("dados") or ContratoDadosForm(
        instance=contrato,
        initial={"regiao_uf": regiao["uf"], "regiao_municipio": regiao["municipio"]},
    )
    formulario_participante = formularios_invalidos.get(
        "adicionar_participante"
    ) or ParticipacaoForm()
    formulario_escopo = formularios_invalidos.get("adicionar_escopo") or EscopoContratoForm()
    formulario_dia = formularios_invalidos.get("salvar_dia") or DiaNaoUtilForm(
        initial={"data": selecionada}
    )
    formularios_participantes = {
        item["participacao"].pk: ParticipacaoEdicaoForm(
            initial={"papel": item["papel_valor"], "funcao": item["funcao"]}
        )
        for item in participantes
    }
    formularios_escopos = {
        item["escopo"].pk: EscopoContratoForm(
            initial={
                "nome": item["escopo"].nome,
                "classes": ", ".join(item["classes"]),
            }
        )
        for item in scopes
    }
    for chave, formulario in formularios_invalidos.items():
        if chave.startswith("participante-"):
            formularios_participantes[int(chave.split("-", 1)[1])] = formulario
        elif chave.startswith("escopo-"):
            formularios_escopos[int(chave.split("-", 1)[1])] = formulario
    for item in participantes:
        item["form"] = formularios_participantes[item["participacao"].pk]
    for item in scopes:
        item["form"] = formularios_escopos[item["escopo"].pk]

    contexto = {
        "resumo": detalhe_contrato(contrato),
        "contrato": contrato,
        "participantes": participantes,
        "escopos": scopes,
        "regiao": regiao,
        "calendario": calendario_contrato(contrato, ano, mes),
        "data_selecionada": selecionada,
        "pode_editar": pode_editar,
        "form_dados": formulario_dados,
        "form_participante": formulario_participante,
        "form_escopo": formulario_escopo,
        "form_dia": formulario_dia,
        "formularios_participantes": formularios_participantes,
        "formularios_escopos": formularios_escopos,
    }
    return render(request, "contratos/detalhe.html", contexto)


def _redirecionar(contrato, ancora=None):
    destino = reverse("contrato_detalhe", args=(contrato.pk,))
    if ancora:
        destino += f"#{ancora}"
    return redirect(destino)


def _redirecionar_calendario(contrato, data):
    destino = reverse("contrato_detalhe", args=(contrato.pk,))
    destino += f"?ano={data.year}&mes={data.month}&data={data.isoformat()}#calendario"
    return redirect(destino)
