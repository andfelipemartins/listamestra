from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from acoes.views import _contrato_da_requisicao

from .forms import TarefaForm
from .models import Tarefa
from .servicos import (
    cancelar_tarefa,
    concluir_tarefa,
    criar_tarefa,
    editar_tarefa,
    equipes_geridas,
    modelos_prazo,
    modelos_status,
    pode_cancelar_tarefa,
    pode_concluir_tarefa,
    pode_editar_tarefa,
    pode_ver_tarefa,
    responsaveis_permitidos,
    consulta_tarefas_com_sugestao,
    models_case_atrasada,
    tarefas_da_equipe,
    tarefas_visiveis,
)


def _contrato(request):
    contrato_id = _contrato_da_requisicao(request)
    return contrato_id


class TarefasListaView(LoginRequiredMixin, View):
    template_name = "tarefas/lista.html"

    def get(self, request):
        contrato_id = _contrato(request)
        if contrato_id is None:
            return redirect("contratos_escolher")
        from acoes.services import resolver_contrato

        contrato = resolver_contrato(request.user, contrato_id)
        aba = request.GET.get("aba", "minhas")
        equipes = equipes_geridas(request.user, contrato)
        if aba == "equipe":
            if not equipes.exists():
                raise PermissionDenied("Você não gere uma equipe neste contrato.")
            base = tarefas_da_equipe(request.user, contrato)
        elif aba == "criadas":
            base = tarefas_visiveis(request.user, contrato).filter(criada_por=request.user)
        else:
            aba = "minhas"
            base = Tarefa.objects.filter(contrato=contrato, responsavel=request.user)

        status = request.GET.get("status", "")
        prazo = request.GET.get("prazo", "")
        tarefas = modelos_prazo(modelos_status(base, status), prazo)
        tarefas = consulta_tarefas_com_sugestao(tarefas).select_related(
            "responsavel", "criada_por", "documento"
        ).order_by(models_case_atrasada(timezone.localdate()), "prazo", "-criada_em", "-pk")
        return render(
            request,
            self.template_name,
            {
                "contrato": contrato,
                "aba": aba,
                "pode_ver_equipe": equipes.exists(),
                "status_selecionado": status,
                "prazo_selecionado": prazo,
                "status_opcoes": Tarefa.Status.choices,
                "tarefas": tarefas,
            },
        )


class TarefaCriarView(LoginRequiredMixin, View):
    template_name = "tarefas/form.html"

    def get(self, request):
        contrato_id = _contrato(request)
        if contrato_id is None:
            return redirect("contratos_escolher")
        from acoes.services import resolver_contrato

        contrato = resolver_contrato(request.user, contrato_id)
        form = TarefaForm(
            contrato=contrato,
            responsaveis=responsaveis_permitidos(request.user, contrato),
            initial={"responsavel": request.user.pk},
        )
        return render(request, self.template_name, {"contrato": contrato, "form": form, "criando": True})

    def post(self, request):
        contrato_id = _contrato(request)
        if contrato_id is None:
            return redirect("contratos_escolher")
        from acoes.services import resolver_contrato

        contrato = resolver_contrato(request.user, contrato_id)
        form = TarefaForm(
            request.POST,
            contrato=contrato,
            responsaveis=responsaveis_permitidos(request.user, contrato),
        )
        if form.is_valid():
            tarefa = criar_tarefa(
                contrato=contrato,
                usuario=request.user,
                **form.cleaned_data,
            )
            messages.success(request, "Tarefa criada.")
            return redirect("tarefas:detalhe", tarefa.pk)
        return render(request, self.template_name, {"contrato": contrato, "form": form, "criando": True})


class TarefaDetalheView(LoginRequiredMixin, View):
    template_name = "tarefas/form.html"

    def _dados(self, request, tarefa_id):
        contrato_id = _contrato(request)
        if contrato_id is None:
            return None, None
        from acoes.services import resolver_contrato

        contrato = resolver_contrato(request.user, contrato_id)
        tarefa = get_object_or_404(
            Tarefa.objects.select_related("contrato", "responsavel", "criada_por", "documento"),
            pk=tarefa_id,
            contrato=contrato,
        )
        if not pode_ver_tarefa(request.user, tarefa):
            raise PermissionDenied("Você não pode ver esta tarefa.")
        return contrato, tarefa

    def get(self, request, tarefa_id):
        contrato, tarefa = self._dados(request, tarefa_id)
        if contrato is None:
            return redirect("contratos_escolher")
        pode_editar = pode_editar_tarefa(request.user, tarefa)
        form = (
            TarefaForm(
                contrato=contrato,
                responsaveis=responsaveis_permitidos(request.user, contrato),
                instance=tarefa,
            )
            if pode_editar
            else None
        )
        historico = tarefa.history.select_related("history_user").order_by("-history_date", "-history_id")
        contexto = {
            "contrato": contrato,
            "tarefa": tarefa,
            "form": form,
            "criando": False,
            "pode_editar": pode_editar,
            "pode_concluir": pode_concluir_tarefa(request.user, tarefa),
            "pode_cancelar": pode_cancelar_tarefa(request.user, tarefa),
            "historico": historico,
        }
        return render(request, self.template_name, contexto)

    def post(self, request, tarefa_id):
        contrato, tarefa = self._dados(request, tarefa_id)
        if contrato is None:
            return redirect("contratos_escolher")
        if not pode_editar_tarefa(request.user, tarefa):
            raise PermissionDenied("Você não pode editar esta tarefa.")
        form = TarefaForm(
            request.POST,
            contrato=contrato,
            responsaveis=responsaveis_permitidos(request.user, contrato),
            instance=tarefa,
        )
        if form.is_valid():
            editar_tarefa(
                tarefa=tarefa,
                usuario=request.user,
                **form.cleaned_data,
            )
            messages.success(request, "Tarefa atualizada.")
            return redirect("tarefas:detalhe", tarefa.pk)
        historico = tarefa.history.select_related("history_user").order_by("-history_date", "-history_id")
        return render(
            request,
            self.template_name,
            {
                "contrato": contrato,
                "tarefa": tarefa,
                "form": form,
                "criando": False,
                "pode_editar": True,
                "pode_concluir": pode_concluir_tarefa(request.user, tarefa),
                "pode_cancelar": pode_cancelar_tarefa(request.user, tarefa),
                "historico": historico,
            },
        )


class TarefaAcaoView(LoginRequiredMixin, View):
    acao = None

    def post(self, request, tarefa_id):
        contrato_id = _contrato(request)
        if contrato_id is None:
            return redirect("contratos_escolher")
        from acoes.services import resolver_contrato

        contrato = resolver_contrato(request.user, contrato_id)
        tarefa = get_object_or_404(Tarefa, pk=tarefa_id, contrato=contrato)
        if self.acao == "concluir":
            concluir_tarefa(tarefa=tarefa, usuario=request.user)
            messages.success(request, "Tarefa concluída.")
        else:
            cancelar_tarefa(tarefa=tarefa, usuario=request.user)
            messages.success(request, "Tarefa cancelada.")
        return redirect("tarefas:detalhe", tarefa.pk)


class TarefaConcluirView(TarefaAcaoView):
    acao = "concluir"


class TarefaCancelarView(TarefaAcaoView):
    acao = "cancelar"
