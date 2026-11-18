from dataclasses import dataclass

from django.db.models import F, Prefetch
from django.utils import timezone

from core.perfil import ErroPerfil, perfil_de_dict
from core.perfil.painel import resumir
from contratos.models import PerfilContrato
from documentos.models import Analise, Documento, Emissao
from importacoes.models import ImportacaoID, ImportacaoSituacao, ItemPrevisto


class PainelIndisponivel(ValueError):
    pass


@dataclass(frozen=True)
class DocumentoPainel:
    documento: Documento
    situacao: str | None


def carregar_painel(contrato, por=None):
    """Monta os dados do painel e dos recortes, sem depender da camada de apresentação."""
    perfil_modelo = PerfilContrato.perfil_vigente(contrato, timezone.localdate())
    if perfil_modelo is None:
        raise PainelIndisponivel("Este contrato ainda não tem um perfil vigente.")
    try:
        perfil = perfil_de_dict(perfil_modelo.definicao)
    except ErroPerfil as erro:
        raise PainelIndisponivel(f"O perfil vigente não pode alimentar o painel: {erro}") from erro

    analises = Analise.objects.order_by(
        F("data_analise").desc(nulls_last=True), "-registrado_em", "-pk"
    )
    emissoes = Emissao.objects.order_by("data_emissao", "pk").prefetch_related(
        Prefetch("analises", queryset=analises)
    )
    itens = (
        ItemPrevisto.objects.filter(
            indice__contrato=contrato,
            indice__vigente=True,
            excluido=False,
        )
        .select_related("documento")
        .prefetch_related(Prefetch("documento__emissoes", queryset=emissoes))
        .order_by("documento__identificador_base", "indice_id")
    )

    previstos = {}
    for item in itens:
        previstos.setdefault(item.documento_id, item.documento)
    documentos_painel = [
        DocumentoPainel(documento, _situacao_atual(documento))
        for documento in previstos.values()
    ]
    situacoes = [item.situacao for item in documentos_painel]
    resumo = resumir(perfil, situacoes)

    ids_previstos = set(previstos)
    fora_do_id = (
        Documento.objects.filter(contrato=contrato, emissoes__isnull=False)
        .exclude(pk__in=ids_previstos)
        .distinct()
        .count()
    )

    caixas = perfil.codigo.campos
    if not caixas:
        raise PainelIndisponivel("O perfil vigente não define caixas para recorte.")
    nomes_caixas = {caixa.nome for caixa in caixas}
    caixa_selecionada = por if por in nomes_caixas else caixas[0].nome
    definicao_caixa = next(caixa for caixa in caixas if caixa.nome == caixa_selecionada)

    por_valor = {}
    for item in documentos_painel:
        bruto = _valor_caixa(item.documento, caixa_selecionada)
        valor = bruto or "(sem informação)"
        registro = por_valor.setdefault(
            valor,
            {
                "valor": valor,
                "rotulo": (definicao_caixa.valores or {}).get(valor, valor),
                "situacoes": [],
            },
        )
        registro["situacoes"].append(item.situacao)

    recortes = []
    grupos_recorte = (*perfil.painel.grupos, resumo.grupos[-1])
    for registro in sorted(por_valor.values(), key=lambda linha: linha["rotulo"].casefold()):
        subtotal = resumir(perfil, registro["situacoes"])
        recortes.append(
            {
                "valor": registro["valor"],
                "rotulo": registro["rotulo"],
                "total": subtotal.total_previsto,
                "contagens": [subtotal.contagens.get(grupo.id, 0) for grupo in grupos_recorte],
            }
        )

    ultima_situacao = (
        ImportacaoSituacao.objects.filter(contrato=contrato)
        .order_by("-data_extracao", "-importado_em", "-pk")
        .first()
    )
    ultima_importacao_id = (
        ImportacaoID.objects.filter(contrato=contrato)
        .order_by("-importado_em", "-pk")
        .first()
    )

    return {
        "contrato": contrato,
        "perfil": perfil,
        "resumo": resumo,
        "total_documentos_previstos": len(documentos_painel),
        "fora_do_id": fora_do_id,
        "ultima_situacao_pw": ultima_situacao.data_extracao if ultima_situacao else None,
        "ultima_importacao_id": timezone.localtime(ultima_importacao_id.importado_em).date()
        if ultima_importacao_id
        else None,
        "caixas": caixas,
        "por": caixa_selecionada,
        "rotulo_caixa": definicao_caixa.rotulo,
        "recortes": recortes,
        "grupos_recorte": grupos_recorte,
    }


def _situacao_atual(documento):
    emissao_mais_recente = max(
        documento.emissoes.all(),
        key=lambda emissao: (emissao.data_emissao, emissao.pk),
        default=None,
    )
    if emissao_mais_recente is None:
        return None
    analise_mais_recente = next(iter(emissao_mais_recente.analises.all()), None)
    return analise_mais_recente.situacao if analise_mais_recente else ""


def _valor_caixa(documento, nome):
    valor = documento.atributos.get(nome)
    if valor is None:
        valor = {"tipo": documento.tipo, "trecho": documento.trecho, "classe": documento.disciplina}.get(nome)
    return str(valor).strip() if valor is not None else ""
