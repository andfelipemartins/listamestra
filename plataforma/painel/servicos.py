from collections.abc import Mapping
from dataclasses import dataclass

from django.db.models import F, Prefetch
from django.utils import timezone

from core.perfil import ErroPerfil, perfil_de_dict
from core.perfil.indicadores import (
    DocumentoIndicador,
    EmissaoIndicador,
    calcular_indicador_aprovacao,
)
from core.perfil.painel import classificar, resumir
from contratos.models import PerfilContrato
from documentos.models import Analise, Documento, Emissao
from importacoes.models import ImportacaoID, ImportacaoSituacao, ItemPrevisto


class PainelIndisponivel(ValueError):
    pass


@dataclass(frozen=True)
class DocumentoPainel:
    documento: Documento
    situacao: str | None


def carregar_painel(contrato, por=None, filtros=None):
    """Monta o resumo e os recortes do painel conforme o perfil vigente."""
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
    todos_documentos = [
        DocumentoPainel(documento, _situacao_atual(documento))
        for documento in previstos.values()
    ]

    filtros_disponiveis = _filtros_disponiveis(perfil.codigo.campos, todos_documentos)
    filtros_selecionados = _normalizar_filtros(filtros, filtros_disponiveis)
    for filtro in filtros_disponiveis:
        valores_selecionados = filtros_selecionados.get(filtro["nome"], set())
        for opcao in filtro["opcoes"]:
            opcao["selecionado"] = opcao["valor"] in valores_selecionados
    filtros_ativos = _resumir_filtros(filtros_disponiveis, filtros_selecionados)
    documentos_filtrados = [
        item for item in todos_documentos if _corresponde_filtros(item.documento, filtros_selecionados)
    ]

    grupos_fora_painel = {
        grupo.id: grupo for grupo in perfil.painel.grupos if not grupo.conta_no_avanco
    }
    contagens_fora_painel = {identificador: 0 for identificador in grupos_fora_painel}
    documentos_em_conta = []
    for item in documentos_filtrados:
        grupo = classificar(perfil, item.situacao)
        if grupo.id in grupos_fora_painel:
            contagens_fora_painel[grupo.id] += 1
        else:
            documentos_em_conta.append(item)

    resumo = resumir(perfil, (item.situacao for item in documentos_em_conta))
    ids_previstos = set(previstos)
    documentos_fora_id = (
        Documento.objects.filter(contrato=contrato, emissoes__isnull=False)
        .exclude(pk__in=ids_previstos)
        .distinct()
    )
    if filtros_selecionados:
        fora_do_id = sum(
            _corresponde_filtros(documento, filtros_selecionados)
            for documento in documentos_fora_id
        )
    else:
        fora_do_id = documentos_fora_id.count()

    caixas = perfil.codigo.campos
    if not caixas:
        raise PainelIndisponivel("O perfil vigente não define caixas para recorte.")
    nomes_caixas = {caixa.nome for caixa in caixas}
    caixa_selecionada = por if por in nomes_caixas else caixas[0].nome
    definicao_caixa = next(caixa for caixa in caixas if caixa.nome == caixa_selecionada)

    indicadores_aprovacao = []
    for indicador in perfil.painel.indicadores:
        documentos_indicador = [
            DocumentoIndicador(
                grupo_id=classificar(perfil, item.situacao).id,
                situacao=item.situacao,
                emissoes=tuple(
                    EmissaoIndicador(
                        fase=emissao.fase,
                        revisao=emissao.revisao,
                        situacao=_situacao_emissao(emissao),
                    )
                    for emissao in item.documento.emissoes.all()
                ),
                recorte=_valor_caixa(item.documento, caixa_selecionada) or "(sem informação)",
            )
            for item in documentos_filtrados
        ]
        resultado = calcular_indicador_aprovacao(perfil, indicador, documentos_indicador)
        recortes_indicador = []
        for valor, contagem in resultado.por_recorte.items():
            rotulo = (definicao_caixa.valores or {}).get(valor, valor)
            recortes_indicador.append(
                {
                    "valor": valor,
                    "rotulo": rotulo,
                    "percentual": contagem.percentual,
                    "tem_dados": contagem.percentual is not None,
                    "dentro_limite": contagem.dentro_limite,
                    "fora_limite": contagem.fora_limite,
                    "base": contagem.base,
                }
            )
        indicadores_aprovacao.append(
            {
                "configuracao": indicador,
                "percentual": resultado.geral.percentual,
                "tem_dados": resultado.geral.percentual is not None,
                "dentro_limite": resultado.geral.dentro_limite,
                "fora_limite": resultado.geral.fora_limite,
                "base": resultado.geral.base,
                "recortes": sorted(
                    recortes_indicador, key=lambda linha: linha["rotulo"].casefold()
                ),
            }
        )

    por_valor = {}
    for item in documentos_em_conta:
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
    grupos_recorte = tuple(
        grupo
        for grupo in resumo.grupos
        if grupo.id == "nao_mapeado" or grupo.conta_no_avanco
    )
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
        "total_documentos_previstos": resumo.total_previsto,
        "total_documentos_id": len(documentos_filtrados),
        "fora_do_painel": [
            {"grupo": grupos_fora_painel[identificador], "quantidade": quantidade}
            for identificador, quantidade in contagens_fora_painel.items()
            if quantidade
        ],
        "fora_do_id": fora_do_id,
        "ultima_situacao_pw": ultima_situacao.data_extracao if ultima_situacao else None,
        "ultima_importacao_id": timezone.localtime(ultima_importacao_id.importado_em).date()
        if ultima_importacao_id
        else None,
        "caixas": caixas,
        "por": caixa_selecionada,
        "rotulo_caixa": definicao_caixa.rotulo,
        "filtros": filtros_disponiveis,
        "filtros_ativos": filtros_ativos,
        "quantidade_filtros_ativos": sum(len(item["valores"]) for item in filtros_ativos),
        "recortes": recortes,
        "grupos_recorte": grupos_recorte,
        "indicadores_aprovacao": indicadores_aprovacao,
    }


def _filtros_disponiveis(caixas, documentos):
    filtros = []
    for caixa in caixas:
        valores_cadastrados = caixa.valores or {}
        if not valores_cadastrados:
            continue
        valores_presentes = {
            _valor_caixa(item.documento, caixa.nome)
            for item in documentos
            if _valor_caixa(item.documento, caixa.nome) in valores_cadastrados
        }
        opcoes = [
            {
                "valor": valor,
                "rotulo": f"{valor} – {rotulo}" if rotulo and rotulo != valor else valor,
            }
            for valor, rotulo in valores_cadastrados.items()
            if str(valor) in valores_presentes
        ]
        if opcoes:
            filtros.append({"nome": caixa.nome, "rotulo": caixa.rotulo, "opcoes": opcoes})
    return filtros


def _normalizar_filtros(filtros, filtros_disponiveis):
    selecionados = {}
    for filtro in filtros_disponiveis:
        if hasattr(filtros, "getlist"):
            solicitados = filtros.getlist(filtro["nome"])
        elif isinstance(filtros, Mapping):
            solicitados = filtros.get(filtro["nome"], [])
        else:
            solicitados = []
        if isinstance(solicitados, str):
            solicitados = [solicitados]
        permitidos = {opcao["valor"] for opcao in filtro["opcoes"]}
        valores = {str(valor) for valor in solicitados if str(valor) in permitidos}
        if valores:
            selecionados[filtro["nome"]] = valores
    return selecionados


def _resumir_filtros(filtros_disponiveis, selecionados):
    ativos = []
    for filtro in filtros_disponiveis:
        valores = selecionados.get(filtro["nome"], set())
        if not valores:
            continue
        rotulos = [
            opcao["rotulo"] for opcao in filtro["opcoes"] if opcao["valor"] in valores
        ]
        ativos.append({"rotulo": filtro["rotulo"], "valores": rotulos})
    return ativos


def _corresponde_filtros(documento, filtros):
    return all(
        _valor_caixa(documento, nome) in valores for nome, valores in filtros.items()
    )


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


def _situacao_emissao(emissao):
    analise_mais_recente = next(iter(emissao.analises.all()), None)
    return analise_mais_recente.situacao if analise_mais_recente else None


def _valor_caixa(documento, nome):
    valor = documento.atributos.get(nome)
    if valor is None:
        valor = {"tipo": documento.tipo, "trecho": documento.trecho, "classe": documento.disciplina}.get(nome)
    return str(valor).strip() if valor is not None else ""
