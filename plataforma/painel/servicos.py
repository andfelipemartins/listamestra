from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date
from math import ceil

from django.db.models import F, Prefetch
from django.utils import timezone

from core.perfil import ErroPerfil, perfil_de_dict
from core.perfil.indicadores import (
    DocumentoIndicador,
    EmissaoIndicador,
    calcular_indicador_aprovacao,
)
from core.perfil.painel import (
    classificar,
    classificar_categoria,
    resolver_situacao_oculta,
    resumir,
)
from contratos.models import PerfilContrato
from .prazos import (
    _valor_caixa,
    calcular_indicador_cronograma,
    calcular_indicadores_prazo,
)
from documentos.models import Analise, Documento, Emissao
from importacoes.models import (
    ImportacaoID,
    ImportacaoSituacao,
    IndiceDocumentos,
    ItemPrevisto,
)


class PainelIndisponivel(ValueError):
    pass


_ID_OUTROS = "__outros__"
_FASE_SEM_FASE = "__sem_fase__"
_FILTRO_FASE = "fase"
_ESCOPO_SEM_ESCOPO = "__sem_escopo__"
_FILTRO_ESCOPO = "escopo"


@dataclass(frozen=True)
class DocumentoPainel:
    documento: Documento
    situacao: str | None
    situacao_vigente: str | None
    situacoes_mais_recentes: tuple[str | None, ...]
    fases: tuple[str, ...] = ()
    escopos: tuple[str, ...] = ()


@dataclass(frozen=True)
class CaixaPainel:
    nome: str
    rotulo: str
    valores: dict


def carregar_painel(contrato, por=None, filtros=None):
    """Monta o resumo e os recortes do painel conforme o perfil vigente."""
    hoje = timezone.localdate()
    perfil_modelo = PerfilContrato.perfil_vigente(contrato, hoje)
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
    indices_vigentes = list(
        IndiceDocumentos.objects.filter(contrato=contrato, vigente=True).prefetch_related(
            "escopos"
        )
    )
    indices_por_id = {indice.pk: indice for indice in indices_vigentes}
    ids_vigentes = set(indices_por_id)
    fases_contaveis = {
        _valor_fase(indice.fase)
        for indice in indices_vigentes
        if indice.conta_no_previsto
    }
    escopos_contaveis = {
        _valor_escopo(escopo.nome)
        for indice in indices_vigentes
        if indice.conta_no_previsto
        for escopo in indice.escopos.all()
    }
    escopos_contaveis.update(
        _ESCOPO_SEM_ESCOPO
        for indice in indices_vigentes
        if indice.conta_no_previsto and not indice.escopos.all()
    )
    itens = (
        ItemPrevisto.objects.filter(indice_id__in=ids_vigentes, excluido=False)
        .select_related("documento")
        .prefetch_related(Prefetch("documento__emissoes", queryset=emissoes))
        .order_by("documento__identificador_base", "indice_id")
    )

    previstos = {}
    documentos_em_ids = set()
    fases_por_documento = {}
    escopos_por_documento = {}
    for item in itens:
        documentos_em_ids.add(item.documento_id)
        indice = indices_por_id[item.indice_id]
        if not indice.conta_no_previsto:
            continue
        previstos.setdefault(item.documento_id, item.documento)
        fases_por_documento.setdefault(item.documento_id, set()).add(
            _valor_fase(indice.fase)
        )
        escopos = {
            _valor_escopo(escopo.nome) for escopo in indice.escopos.all()
        } or {_ESCOPO_SEM_ESCOPO}
        escopos_por_documento.setdefault(item.documento_id, set()).update(escopos)
    todos_documentos = []
    for documento in previstos.values():
        situacao_vigente = _situacao_atual(documento)
        historico = _historico_situacoes(documento)
        grupo_atual = classificar(perfil, situacao_vigente)
        situacao_painel = (
            resolver_situacao_oculta(perfil, historico)
            if grupo_atual.oculto_no_painel
            else situacao_vigente
        )
        todos_documentos.append(
            DocumentoPainel(
                documento,
                situacao_painel,
                situacao_vigente,
                historico,
                tuple(sorted(fases_por_documento[documento.pk], key=str.casefold)),
                tuple(
                    sorted(
                        escopos_por_documento[documento.pk],
                        key=_chave_ordenacao_escopo,
                    )
                ),
            )
        )

    filtros_disponiveis = _filtros_disponiveis(perfil.codigo.campos, todos_documentos)
    caixa_fase = None
    fases_ordenadas = sorted(fases_contaveis, key=_chave_ordenacao_fase)
    if len(fases_contaveis) > 1:
        caixa_fase = CaixaPainel(
            nome=_FILTRO_FASE,
            rotulo="Fase",
            valores={fase: _rotulo_fase(fase) for fase in fases_ordenadas},
        )
        filtros_disponiveis.append(
            {
                "nome": _FILTRO_FASE,
                "rotulo": "Fase",
                "opcoes": [
                    {"valor": fase, "rotulo": _rotulo_fase(fase)}
                    for fase in fases_ordenadas
                ],
            }
        )
    caixa_escopo = None
    escopos_ordenados = sorted(escopos_contaveis, key=_chave_ordenacao_escopo)
    if len(escopos_contaveis) > 1:
        caixa_escopo = CaixaPainel(
            nome=_FILTRO_ESCOPO,
            rotulo="Escopo do ID",
            valores={escopo: _rotulo_escopo(escopo) for escopo in escopos_ordenados},
        )
        filtros_disponiveis.append(
            {
                "nome": _FILTRO_ESCOPO,
                "rotulo": "Escopo do ID",
                "opcoes": [
                    {"valor": escopo, "rotulo": _rotulo_escopo(escopo)}
                    for escopo in escopos_ordenados
                ],
            }
        )
    if perfil.painel.categorias:
        filtros_disponiveis.append(_filtro_categorias(perfil, todos_documentos))
    filtros_selecionados = _normalizar_filtros(filtros, filtros_disponiveis)
    for filtro in filtros_disponiveis:
        valores_selecionados = filtros_selecionados.get(filtro["nome"], set())
        for opcao in filtro["opcoes"]:
            opcao["selecionado"] = opcao["valor"] in valores_selecionados
    filtros_ativos = _resumir_filtros(filtros_disponiveis, filtros_selecionados)
    documentos_filtrados = [
        item
        for item in todos_documentos
        if _corresponde_filtros(
            item.documento,
            filtros_selecionados,
            perfil,
            item.fases,
            item.escopos,
        )
    ]

    grupos_fora_painel = {
        grupo.id: grupo
        for grupo in perfil.painel.grupos
        if not grupo.conta_no_avanco and not grupo.oculto_no_painel
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
    documentos_fora_id = (
        Documento.objects.filter(contrato=contrato, emissoes__isnull=False)
        .exclude(pk__in=documentos_em_ids)
        .distinct()
    )
    if filtros_selecionados:
        fora_do_id = sum(
            _corresponde_filtros(documento, filtros_selecionados, perfil)
            for documento in documentos_fora_id
        )
    else:
        fora_do_id = documentos_fora_id.count()

    caixas = list(perfil.codigo.campos)
    if not caixas:
        raise PainelIndisponivel("O perfil vigente não define caixas para recorte.")
    if caixa_fase is not None:
        caixas.append(caixa_fase)
    if caixa_escopo is not None:
        caixas.append(caixa_escopo)
    nomes_caixas = {caixa.nome for caixa in caixas}
    nome_categoria = "categoria"
    caixa_selecionada = (
        por
        if por in nomes_caixas or (por == nome_categoria and perfil.painel.categorias)
        else caixas[0].nome
    )
    definicao_caixa = next(
        (caixa for caixa in caixas if caixa.nome == caixa_selecionada), None
    )
    rotulo_caixa = (
        "Categoria" if caixa_selecionada == nome_categoria else definicao_caixa.rotulo
    )

    def valor_recorte(perfil_recorte, documento, nome):
        return _valor_recorte(
            perfil_recorte,
            documento,
            nome,
            fases_por_documento,
            escopos_por_documento,
        )

    indicadores_prazo, analises_deduzidas_sem_data = calcular_indicadores_prazo(
        perfil,
        documentos_filtrados,
        caixa_selecionada,
        definicao_caixa,
        hoje,
        valor_recorte=valor_recorte,
        rotulo_recorte=_rotulo_recorte,
    )
    indicador_cronograma = calcular_indicador_cronograma(
        contrato,
        perfil,
        documentos_filtrados,
        caixa_selecionada,
        definicao_caixa,
        hoje,
        valor_recorte=valor_recorte,
        rotulo_recorte=_rotulo_recorte,
    )
    dimensoes_id = {
        _FILTRO_FASE: (fases_ordenadas, "fases", _rotulo_fase),
        _FILTRO_ESCOPO: (escopos_ordenados, "escopos", _rotulo_escopo),
    }
    if caixa_selecionada in dimensoes_id:
        valores_dimensao, atributo_dimensao, _ = dimensoes_id[caixa_selecionada]
        indicadores_prazo_por_dimensao = {}
        cronograma_por_dimensao = {}
        for valor_dimensao in valores_dimensao:
            documentos_dimensao = [
                item
                for item in documentos_filtrados
                if valor_dimensao in getattr(item, atributo_dimensao)
            ]

            def valor_recorte_dimensao(perfil_recorte, documento, nome):
                if nome == caixa_selecionada:
                    return valor_dimensao
                return _valor_recorte(perfil_recorte, documento, nome)

            indicadores_prazo_dimensao, _ = calcular_indicadores_prazo(
                perfil,
                documentos_dimensao,
                caixa_selecionada,
                definicao_caixa,
                hoje,
                valor_recorte=valor_recorte_dimensao,
                rotulo_recorte=_rotulo_recorte,
            )
            indicadores_prazo_por_dimensao[valor_dimensao] = indicadores_prazo_dimensao
            if indicador_cronograma is not None:
                cronograma_por_dimensao[valor_dimensao] = calcular_indicador_cronograma(
                    contrato,
                    perfil,
                    documentos_dimensao,
                    caixa_selecionada,
                    definicao_caixa,
                    hoje,
                    valor_recorte=valor_recorte_dimensao,
                    rotulo_recorte=_rotulo_recorte,
                )
        for indice, indicador in enumerate(indicadores_prazo):
            indicador["recortes"] = [
                recorte
                for valor_dimensao in valores_dimensao
                for recorte in indicadores_prazo_por_dimensao[valor_dimensao][indice]["recortes"]
            ]
        if indicador_cronograma is not None:
            indicador_cronograma["recortes"] = [
                recorte
                for valor_dimensao in valores_dimensao
                for recorte in cronograma_por_dimensao[valor_dimensao]["recortes"]
            ]

    indicadores_aprovacao = []
    for indicador in perfil.painel.indicadores:
        documentos_indicador = [
            DocumentoIndicador(
                grupo_id=classificar(perfil, item.situacao_vigente).id,
                situacao=item.situacao_vigente,
                emissoes=tuple(
                    EmissaoIndicador(
                        fase=emissao.fase,
                        revisao=emissao.revisao,
                        situacao=_situacao_emissao(emissao),
                        versao=emissao.versao,
                        situacoes_mais_recentes=tuple(
                            analise.situacao for analise in emissao.analises.all()
                        ),
                    )
                    for emissao in item.documento.emissoes.all()
                ),
                recorte=valor_recorte(perfil, item.documento, caixa_selecionada)
                or "(sem informação)",
                situacoes_mais_recentes=item.situacoes_mais_recentes,
            )
            for item in documentos_filtrados
        ]
        resultado = calcular_indicador_aprovacao(perfil, indicador, documentos_indicador)
        recortes_indicador = []
        if caixa_selecionada in dimensoes_id:
            valores_dimensao, atributo_dimensao, rotular_dimensao = dimensoes_id[
                caixa_selecionada
            ]
            for valor_dimensao in valores_dimensao:
                documentos_dimensao = [
                    replace(documento_indicador, recorte=valor_dimensao)
                    for documento_indicador, item in zip(
                        documentos_indicador, documentos_filtrados
                    )
                    if valor_dimensao in getattr(item, atributo_dimensao)
                ]
                contagem = calcular_indicador_aprovacao(
                    perfil, indicador, documentos_dimensao
                ).geral
                recortes_indicador.append(
                    {
                        "valor": valor_dimensao,
                        "rotulo": rotular_dimensao(valor_dimensao),
                        "percentual": contagem.percentual,
                        "tem_dados": contagem.percentual is not None,
                        "dentro_limite": contagem.dentro_limite,
                        "fora_limite": contagem.fora_limite,
                        "base": contagem.base,
                        "distribuicao": _faixas_distribuicao(
                            contagem.distribuicao, indicador
                        ),
                    }
                )
        else:
            for valor, contagem in resultado.por_recorte.items():
                rotulo = _rotulo_recorte(perfil, caixa_selecionada, valor, definicao_caixa)
                recortes_indicador.append(
                    {
                        "valor": valor,
                        "rotulo": rotulo,
                        "percentual": contagem.percentual,
                        "tem_dados": contagem.percentual is not None,
                        "dentro_limite": contagem.dentro_limite,
                        "fora_limite": contagem.fora_limite,
                        "base": contagem.base,
                        "distribuicao": _faixas_distribuicao(contagem.distribuicao, indicador),
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
                "distribuicao": _faixas_distribuicao(
                    resultado.geral.distribuicao, indicador
                ),
                "grafico_distribuicao": _grafico_distribuicao(
                    resultado.geral.distribuicao, indicador
                ),
                "recortes": sorted(
                    recortes_indicador, key=lambda linha: linha["rotulo"].casefold()
                ),
            }
        )

    por_valor = {}
    for item in documentos_em_conta:
        for valor in _valores_recorte(perfil, item, caixa_selecionada):
            registro = por_valor.setdefault(
                valor,
                {
                    "valor": valor,
                    "rotulo": _rotulo_recorte(
                        perfil, caixa_selecionada, valor, definicao_caixa
                    ),
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

    categoria_cards = _cartoes_categorias(perfil, documentos_em_conta, todos_documentos)

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
        "categorias": perfil.painel.categorias,
        "categoria_cards": categoria_cards,
        "por": caixa_selecionada,
        "rotulo_caixa": rotulo_caixa,
        "filtros": filtros_disponiveis,
        "filtros_ativos": filtros_ativos,
        "quantidade_filtros_ativos": sum(len(item["valores"]) for item in filtros_ativos),
        "recortes": recortes,
        "grupos_recorte": grupos_recorte,
        "indicadores_aprovacao": indicadores_aprovacao,
        "indicadores_prazo": indicadores_prazo,
        "indicador_cronograma": indicador_cronograma,
        "meta_prazo_percentual": (
            perfil.prazos.meta_percentual if perfil.prazos is not None else None
        ),
        "analises_deduzidas_sem_data": analises_deduzidas_sem_data,
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


def _filtro_categorias(perfil, documentos):
    categorias = {categoria.id: categoria.rotulo for categoria in perfil.painel.categorias}
    valores_presentes = {
        _id_categoria(perfil, item.documento) for item in documentos
    }
    opcoes = [
        {"valor": categoria_id, "rotulo": rotulo}
        for categoria_id, rotulo in categorias.items()
        if categoria_id in valores_presentes
    ]
    if _ID_OUTROS in valores_presentes:
        opcoes.append({"valor": _ID_OUTROS, "rotulo": "Outros"})
    return {"nome": "categoria", "rotulo": "Categoria", "opcoes": opcoes}


def _valor_fase(fase):
    return fase.strip() if fase and fase.strip() else _FASE_SEM_FASE


def _valor_escopo(escopo):
    return escopo.strip() if escopo and escopo.strip() else _ESCOPO_SEM_ESCOPO


def _rotulo_fase(fase):
    return "Sem fase" if fase == _FASE_SEM_FASE else fase


def _rotulo_escopo(escopo):
    return "Sem escopo" if escopo == _ESCOPO_SEM_ESCOPO else escopo


def _chave_ordenacao_fase(fase):
    return (fase == _FASE_SEM_FASE, fase.casefold())


def _chave_ordenacao_escopo(escopo):
    return (escopo == _ESCOPO_SEM_ESCOPO, escopo.casefold())


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


def _corresponde_filtros(documento, filtros, perfil=None, fases=(), escopos=()):
    for nome, valores in filtros.items():
        if nome == _FILTRO_FASE:
            if not set(fases).intersection(valores):
                return False
        elif nome == _FILTRO_ESCOPO:
            if not set(escopos).intersection(valores):
                return False
        elif nome == "categoria" and perfil is not None and perfil.painel.categorias:
            if _id_categoria(perfil, documento) not in valores:
                return False
        elif _valor_caixa(documento, nome) not in valores:
            return False
    return True


def _id_categoria(perfil, documento):
    valores_caixas = {
        caixa.nome: _valor_caixa(documento, caixa.nome) for caixa in perfil.codigo.campos
    }
    categoria = classificar_categoria(perfil, valores_caixas)
    return categoria.id if categoria is not None else _ID_OUTROS


def _valor_recorte(
    perfil,
    documento,
    nome,
    fases_por_documento=None,
    escopos_por_documento=None,
):
    if nome == "categoria" and perfil.painel.categorias:
        return _id_categoria(perfil, documento)
    if nome == _FILTRO_FASE:
        fases = (fases_por_documento or {}).get(documento.pk, ())
        return sorted(fases, key=_chave_ordenacao_fase)[0] if fases else ""
    if nome == _FILTRO_ESCOPO:
        escopos = (escopos_por_documento or {}).get(documento.pk, ())
        return sorted(escopos, key=_chave_ordenacao_escopo)[0] if escopos else ""
    return _valor_caixa(documento, nome)


def _valores_recorte(perfil, item, nome):
    if nome == _FILTRO_FASE:
        return item.fases
    if nome == _FILTRO_ESCOPO:
        return item.escopos
    return (_valor_recorte(perfil, item.documento, nome),)


def _rotulo_recorte(perfil, nome, valor, definicao_caixa):
    if nome == "categoria" and perfil.painel.categorias:
        if valor == _ID_OUTROS:
            return "Outros"
        return next(
            (categoria.rotulo for categoria in perfil.painel.categorias if categoria.id == valor),
            valor,
        )
    if nome == _FILTRO_FASE:
        return _rotulo_fase(valor)
    if nome == _FILTRO_ESCOPO:
        return _rotulo_escopo(valor)
    return (definicao_caixa.valores or {}).get(valor, valor)


def _cartoes_categorias(perfil, documentos_em_conta, todos_documentos):
    if not perfil.painel.categorias:
        return []
    categorias = [(categoria.id, categoria.rotulo) for categoria in perfil.painel.categorias]
    if any(_id_categoria(perfil, item.documento) == _ID_OUTROS for item in todos_documentos):
        categorias.append((_ID_OUTROS, "Outros"))

    grupos_resumo = tuple(
        grupo
        for grupo in perfil.painel.grupos
        if grupo.conta_no_avanco and not grupo.oculto_no_painel
    )
    cartoes = []
    for categoria_id, rotulo in categorias:
        documentos_categoria = [
            item
            for item in documentos_em_conta
            if _id_categoria(perfil, item.documento) == categoria_id
        ]
        resumo_categoria = resumir(
            perfil, (item.situacao for item in documentos_categoria)
        )
        cartoes.append(
            {
                "id": categoria_id,
                "rotulo": rotulo,
                "total": resumo_categoria.total_previsto,
                "grupos": [
                    {
                        "rotulo": grupo.rotulo,
                        "quantidade": resumo_categoria.contagens.get(grupo.id, 0),
                    }
                    for grupo in grupos_resumo
                ],
            }
        )
    return cartoes


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


def _historico_situacoes(documento):
    emissoes = sorted(
        documento.emissoes.all(),
        key=lambda emissao: (emissao.data_emissao, emissao.pk),
        reverse=True,
    )
    return tuple(
        analise.situacao
        for emissao in emissoes
        for analise in emissao.analises.all()
    )


def _situacao_emissao(emissao):
    analise_mais_recente = next(iter(emissao.analises.all()), None)
    return analise_mais_recente.situacao if analise_mais_recente else None


def _faixas_distribuicao(distribuicao, indicador):
    faixas = []
    for numero, quantidade in enumerate(distribuicao):
        if numero == 0:
            rotulo = "Emissão Inicial"
        elif numero == indicador.agrupar_a_partir:
            rotulo = f"Rev. {numero}+"
        else:
            rotulo = f"Rev. {numero}"
        faixas.append(
            {
                "rotulo": rotulo,
                "quantidade": quantidade,
                "dentro_limite": numero <= indicador.limite_revisoes,
            }
        )
    return faixas


def _grafico_distribuicao(distribuicao, indicador):
    faixas = _faixas_distribuicao(distribuicao, indicador)
    quantidade_faixas = max(len(faixas), 1)
    largura = max(700, quantidade_faixas * 104 + 80)
    altura = 260
    esquerda = 48
    direita = 20
    topo = 28
    base = 194
    area_altura = base - topo
    passo = (largura - esquerda - direita) / quantidade_faixas
    largura_barra = min(58, passo * 0.58)
    maximo = max((faixa["quantidade"] for faixa in faixas), default=0) or 1

    marcacoes = sorted(
        {
            0,
            ceil(maximo * 0.25),
            ceil(maximo * 0.5),
            ceil(maximo * 0.75),
            maximo,
        }
    )
    grades = [
        {"valor": valor, "y": base - (valor / maximo) * area_altura}
        for valor in marcacoes
    ]
    barras = []
    for indice, faixa in enumerate(faixas):
        valor = faixa["quantidade"]
        altura_barra = (valor / maximo) * area_altura
        x = esquerda + indice * passo + (passo - largura_barra) / 2
        y = base - altura_barra
        barras.append(
            {
                **faixa,
                "x": x,
                "y": y,
                "centro_x": x + largura_barra / 2,
                "largura": largura_barra,
                "altura": altura_barra,
                "rotulo_y": max(topo + 14, y - 7),
                "titulo": f"{faixa['rotulo']}: {valor} aprovado(s)",
            }
        )

    x_meta = esquerda + passo * (indicador.limite_revisoes + 1)
    return {
        "largura": largura,
        "altura": altura,
        "esquerda": esquerda,
        "direita": largura - direita,
        "topo": topo,
        "base": base,
        "x_meta": x_meta,
        "grades": grades,
        "barras": barras,
    }
