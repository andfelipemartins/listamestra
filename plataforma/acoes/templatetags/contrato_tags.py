from django import template

from contratos.models import Contrato


register = template.Library()


@register.simple_tag
def contrato_ativo(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None
    contrato_id = request.session.get("contrato_ativo_id")
    if not contrato_id:
        return None

    contratos = Contrato.objects.filter(pk=contrato_id, ativo=True)
    if not user.is_staff:
        contratos = contratos.filter(
            participacoes__usuario=user,
            participacoes__ativo=True,
        )
    return contratos.first()
