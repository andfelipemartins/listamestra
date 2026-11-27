from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render

from .models import Contrato
from .servicos import detalhe_contrato, listar_contratos


@login_required
def contratos_lista(request):
    if not request.user.is_staff:
        raise PermissionDenied
    return render(
        request,
        "contratos/lista.html",
        {"contratos": listar_contratos()},
    )


@login_required
def contrato_detalhe(request, contrato_id):
    if not request.user.is_staff:
        raise PermissionDenied
    contrato = get_object_or_404(Contrato, pk=contrato_id)
    return render(
        request,
        "contratos/detalhe.html",
        {"resumo": detalhe_contrato(contrato)},
    )
