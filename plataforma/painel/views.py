from datetime import datetime, timedelta

from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from contratos.models import Contrato, Participacao
from .servicos import PainelIndisponivel, carregar_painel


_PALETA = ("#64748b", "#1769aa", "#2e8b62", "#c27a19", "#bf514b", "#7857a5")


class PainelView(View):
    def get(self, request, contrato_id):
        contrato = get_object_or_404(Contrato, pk=contrato_id, ativo=True)
        acesso, erro = _verificar_acesso(request, contrato)
        if not acesso:
            return render(request, "painel/pin.html", {"contrato": contrato, "erro": erro})
        return _render_painel(request, contrato)

    def post(self, request, contrato_id):
        contrato = get_object_or_404(Contrato, pk=contrato_id, ativo=True)
        acesso, erro = _verificar_acesso(request, contrato, verificar_pin=True)
        if acesso:
            return redirect("painel", contrato_id=contrato.pk)
        return render(request, "painel/pin.html", {"contrato": contrato, "erro": erro})


class PainelRecorteView(View):
    def get(self, request, contrato_id):
        contrato = get_object_or_404(Contrato, pk=contrato_id, ativo=True)
        acesso, erro = _verificar_acesso(request, contrato)
        if not acesso:
            return render(request, "painel/pin.html", {"contrato": contrato, "erro": erro})
        try:
            contexto = _contexto_painel(contrato, request.GET.get("por"))
        except PainelIndisponivel as erro:
            return render(request, "painel/indisponivel.html", {"contrato": contrato, "erro": erro})
        return render(request, "painel/_recortes.html", contexto)


def _verificar_acesso(request, contrato, verificar_pin=False):
    if request.user.is_authenticated and Participacao.objects.filter(
        usuario=request.user, contrato=contrato, ativo=True
    ).exists():
        return True, ""

    chave_liberacao = f"painel_liberado_{contrato.pk}"
    if request.session.get(chave_liberacao):
        return True, ""

    chave_tentativas = f"painel_pin_{contrato.pk}"
    estado = request.session.get(chave_tentativas, {})
    bloqueio = estado.get("bloqueado_ate")
    if bloqueio:
        fim_bloqueio = datetime.fromisoformat(bloqueio)
        if timezone.now() < fim_bloqueio:
            restante = max(1, int((fim_bloqueio - timezone.now()).total_seconds() // 60) + 1)
            return False, f"Muitas tentativas. Tente novamente em cerca de {restante} minutos."
        request.session.pop(chave_tentativas, None)
        estado = {}

    if not contrato.pin_painel:
        return False, "O PIN deste painel ainda não foi configurado pela administração."
    if not verificar_pin:
        return False, ""

    if contrato.verificar_pin_painel(request.POST.get("pin", "")):
        request.session[chave_liberacao] = True
        request.session.pop(chave_tentativas, None)
        return True, ""

    tentativas = int(estado.get("tentativas", 0)) + 1
    if tentativas >= 5:
        request.session[chave_tentativas] = {
            "tentativas": tentativas,
            "bloqueado_ate": (timezone.now() + timedelta(minutes=5)).isoformat(),
        }
        return False, "Muitas tentativas. O acesso ficará bloqueado por 5 minutos."
    request.session[chave_tentativas] = {"tentativas": tentativas}
    restantes = 5 - tentativas
    return False, f"PIN incorreto. Restam {restantes} tentativas antes do bloqueio de 5 minutos."


def _render_painel(request, contrato):
    try:
        contexto = _contexto_painel(contrato, request.GET.get("por"))
    except PainelIndisponivel as erro:
        return render(request, "painel/indisponivel.html", {"contrato": contrato, "erro": erro})
    response = render(request, "painel/index.html", contexto)
    response["Cache-Control"] = "private, no-store"
    return response


def _contexto_painel(contrato, por):
    dados = carregar_painel(contrato, por)
    resumo = dados["resumo"]
    total = dados["total_documentos_previstos"]
    grupo_cards = [
        {
            "grupo": grupo,
            "quantidade": resumo.contagens.get(grupo.id, 0),
            "percentual": round(100 * resumo.contagens.get(grupo.id, 0) / total, 1) if total else 0,
        }
        for grupo in dados["perfil"].painel.grupos
    ]
    chart_groups = list(resumo.grupos)
    for indice, grupo in enumerate(chart_groups):
        if not grupo.cor:
            chart_groups[indice] = type(grupo)(
                id=grupo.id,
                rotulo=grupo.rotulo,
                cor=_PALETA[indice % len(_PALETA)],
                estados=grupo.estados,
                sem_emissao=grupo.sem_emissao,
                conta_no_avanco=grupo.conta_no_avanco,
            )
    dados["grupo_cards"] = grupo_cards
    dados["percentual_avanco"] = resumo.percentual_avanco
    dados["estados_nao_mapeados"] = resumo.estados_nao_mapeados
    dados["grafico_pizza"] = {
        "labels": [grupo.rotulo for grupo in chart_groups],
        "datasets": [
            {
                "data": [resumo.contagens.get(grupo.id, 0) for grupo in chart_groups],
                "backgroundColor": [grupo.cor for grupo in chart_groups],
                "borderWidth": 2,
                "borderColor": "#ffffff",
            }
        ],
    }
    dados["grafico_recortes"] = {
        "labels": [item["rotulo"] for item in dados["recortes"]],
        "datasets": [
            {
                "label": grupo.rotulo,
                "data": [item["contagens"][indice] for item in dados["recortes"]],
                "backgroundColor": grupo.cor or _PALETA[indice % len(_PALETA)],
                "borderWidth": 0,
            }
            for indice, grupo in enumerate(dados["grupos_recorte"])
        ],
    }
    return dados
