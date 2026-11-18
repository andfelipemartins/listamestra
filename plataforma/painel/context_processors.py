from contratos.models import Contrato


def contratos_do_painel(request):
    if not request.user.is_authenticated:
        return {"contratos_painel": ()}
    contratos = Contrato.objects.filter(
        ativo=True,
        participacoes__usuario=request.user,
        participacoes__ativo=True,
    ).distinct()
    return {"contratos_painel": contratos}
