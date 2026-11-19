from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from math import ceil

from django.db.models import F, Prefetch
from django.utils import timezone

from core.perfil import ErroPerfil, perfil_de_dict
from core.perfil.feriados import feriados_nacionais
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
from core.perfil.prazos import avaliar as avaliar_prazo, indicador as resumir_prazos
from contratos.models import PerfilContrato
from documentos.models import Analise, Documento, Emissao
from importacoes.cronograma import comparar_previsoes_cronograma
from importacoes.models import (
    ImportacaoID,
    ImportacaoSituacao,
    ItemPrevisto,
    PrevisaoEmissao,
)


class PainelIndisponivel(ValueError):
    pass


_ID_OUTROS = "__outros__"


@dataclass(frozen=True)
class DocumentoPainel:
    documento: Documento
    situacao: str | None
    situacao_vigente: str | None
    situacoes_mais_recentes: tuple[str | None, ...]


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
            DocumentoPainel(documento, situacao_painel, situacao_vigente, historico)
        )

    filtros_disponiveis = _filtros_disponiveis(perfil.codigo.campos, todos_documentos)
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
        if _corresponde_filtros(item.documento, filtros_selecionados, perfil)
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
    ids_previstos = set(previstos)
    documentos_fora_id = (
        Documento.objects.filter(contrato=contrato, emissoes__isnull=False)
        .exclude(pk__in=ids_previstos)
        .distinct()
    )
    if filtros_selecionados:
        fora_do_id = sum(
            _corresponde_filtros(documento, filtros_selecionados, perfil)
            for documento in documentos_fora_id
        )
    else:
        fora_do_id = documentos_fora_id.count()

    caixas = perfil.codigo.campos
    if not caixas:
        raise PainelIndisponivel("O perfil vigente não define caixas para recorte.")
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

    indicadores_prazo, analises_deduzidas_sem_data = _calcular_indicadores_prazo(
        perfil,
        documentos_filtrados,
        caixa_selecionada,
        definicao_caixa,
        hoje,
    )
    indicador_cronograma = _calcular_indicador_cronograma(
        contrato,
        perfil,
        documentos_filtrados,
        caixa_selecionada,
        definicao_caixa,
        hoje,
    )

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
                recorte=_valor_recorte(perfil, item.documento, caixa_selecionada)
                or "(sem informação)",
                situacoes_mais_recentes=item.situacoes_mais_recentes,
            )
            for item in documentos_filtrados
        ]
        resultado = calcular_indicador_aprovacao(perfil, indicador, documentos_indicador)
        recortes_indicador = []
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
        bruto = _valor_recorte(perfil, item.documento, caixa_selecionada)
        valor = bruto or "(sem informação)"
        registro = por_valor.setdefault(
            valor,
            {
                "valor": valor,
                "rotulo": _rotulo_recorte(perfil, caixa_selecionada, valor, definicao_caixa),
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


def _calcular_indicador_cronograma(
    contrato, perfil, documentos, caixa_selecionada, definicao_caixa, hoje
):
    if not PrevisaoEmissao.objects.filter(contrato=contrato).exists():
        return None

    documentos_por_id = {item.documento.pk: item.documento for item in documentos}
    resultados = comparar_previsoes_cronograma(contrato, hoje=hoje)
    recortes = {}
    for documento in documentos_por_id.values():
        valor = _valor_recorte(perfil, documento, caixa_selecionada) or "(sem informação)"
        recortes.setdefault(
            valor,
            {
                "valor": valor,
                "rotulo": _rotulo_recorte(
                    perfil, caixa_selecionada, valor, definicao_caixa
                ),
                "no_prazo": 0,
                "atrasados": 0,
                "vencidos_sem_emissao": 0,
                "futuros": 0,
                "previstos": 0,
            },
        )

    contagens = {
        "no_prazo": 0,
        "atrasados": 0,
        "vencidos_sem_emissao": 0,
        "futuros": 0,
        "previstos": 0,
    }
    chaves_status = {
        "no_prazo": "no_prazo",
        "atrasado": "atrasados",
        "vencido_sem_emissao": "vencidos_sem_emissao",
        "futuro": "futuros",
    }
    for resultado in resultados:
        documento = documentos_por_id.get(resultado.previsao.documento_id)
        if documento is None:
            continue
        chave = chaves_status[resultado.status]
        contagens[chave] += 1
        contagens["previstos"] += 1
        valor = _valor_recorte(perfil, documento, caixa_selecionada) or "(sem informação)"
        recortes[valor][chave] += 1
        recortes[valor]["previstos"] += 1

    base = contagens["no_prazo"] + contagens["atrasados"] + contagens["vencidos_sem_emissao"]
    meta_percentual = perfil.prazos.meta_percentual if perfil.prazos is not None else None
    for recorte in recortes.values():
        recorte["base"] = (
            recorte["no_prazo"]
            + recorte["atrasados"]
            + recorte["vencidos_sem_emissao"]
        )
        recorte["percentual"] = (
            recorte["no_prazo"] * 100.0 / recorte["base"]
            if recorte["base"]
            else None
        )
        recorte["tem_dados"] = recorte["base"] > 0

    return {
        **contagens,
        "base": base,
        "percentual": contagens["no_prazo"] * 100.0 / base if base else None,
        "tem_dados": base > 0,
        "meta_percentual": meta_percentual,
        "recortes": sorted(recortes.values(), key=lambda item: item["rotulo"].casefold()),
    }


def _calcular_indicadores_prazo(perfil, documentos, caixa_selecionada, definicao_caixa, hoje):
    prazos = perfil.prazos
    if prazos is None or not prazos.regras:
        return [], 0

    feriados = _feriados_prazo(prazos, documentos, hoje)
    indicadores = []
    analises_sem_data = set()
    recortes_documentos = {}
    for item in documentos:
        valor = _valor_recorte(perfil, item.documento, caixa_selecionada) or "(sem informação)"
        rotulo = _rotulo_recorte(perfil, caixa_selecionada, valor, definicao_caixa)
        recortes_documentos.setdefault(valor, rotulo)

    for regra in prazos.regras:
        avaliacoes = []
        por_recorte = {valor: [] for valor in recortes_documentos}
        for item in documentos:
            registro, sem_data = _avaliacoes_da_regra(
                perfil, regra, item.documento, hoje, feriados
            )
            analises_sem_data.update(sem_data)
            valor = _valor_recorte(perfil, item.documento, caixa_selecionada) or "(sem informação)"
            for avaliacao in registro:
                avaliacoes.append(avaliacao)
                por_recorte[valor].append(avaliacao)

        geral = _resumo_prazo(avaliacoes)
        recortes = []
        for valor, rotulo in sorted(
            recortes_documentos.items(), key=lambda item: item[1].casefold()
        ):
            resumo = _resumo_prazo(por_recorte[valor])
            recortes.append({"valor": valor, "rotulo": rotulo, **resumo})
        indicadores.append(
            {
                "regra": regra,
                **geral,
                "recortes": recortes,
            }
        )

    return indicadores, len(analises_sem_data)


def _avaliacoes_da_regra(perfil, regra, documento, hoje, feriados):
    emissoes = sorted(
        documento.emissoes.all(), key=lambda emissao: (emissao.data_emissao, emissao.pk)
    )
    analises_sem_data = set()
    avaliacoes = []
    sigla = _valor_caixa(documento, "tipo") or documento.tipo

    if regra.inicio == "emissao" and regra.fim == "analise":
        for emissao in emissoes:
            analises = list(emissao.analises.all())
            elegiveis = [
                analise
                for analise in analises
                if _analise_no_grupo(perfil, regra, analise)
            ]
            analises_sem_data.update(
                analise.pk
                for analise in elegiveis
                if analise.origem == Analise.Origem.DEDUZIDO_PW
                and analise.data_analise is None
            )
            datadas = [analise for analise in elegiveis if analise.data_analise is not None]
            if datadas:
                analise_final = max(
                    datadas, key=lambda analise: (analise.data_analise, analise.pk)
                )
                data_fim = analise_final.data_analise
                grupo = classificar(perfil, analise_final.situacao).id
            elif not analises and not regra.so_quando_grupo:
                data_fim = None
                grupo = None
            else:
                continue
            avaliacao = avaliar_prazo(
                regra,
                emissao.data_emissao,
                data_fim,
                hoje,
                sigla=sigla,
                grupo=grupo,
                feriados=feriados,
            )
            if avaliacao is not None:
                avaliacoes.append(avaliacao)

    elif regra.inicio == "analise" and regra.fim == "proxima_emissao":
        for indice, emissao in enumerate(emissoes):
            analises = [
                analise
                for analise in emissao.analises.all()
                if _analise_no_grupo(perfil, regra, analise)
            ]
            analises_sem_data.update(
                analise.pk
                for analise in analises
                if analise.origem == Analise.Origem.DEDUZIDO_PW
                and analise.data_analise is None
            )
            datadas = [analise for analise in analises if analise.data_analise is not None]
            if not datadas:
                continue
            analise_revisao = max(
                datadas, key=lambda analise: (analise.data_analise, analise.pk)
            )
            proxima_emissao = emissoes[indice + 1] if indice + 1 < len(emissoes) else None
            avaliacao = avaliar_prazo(
                regra,
                analise_revisao.data_analise,
                proxima_emissao.data_emissao if proxima_emissao else None,
                hoje,
                sigla=sigla,
                grupo=classificar(perfil, analise_revisao.situacao).id,
                feriados=feriados,
            )
            if avaliacao is not None:
                avaliacoes.append(avaliacao)

    return avaliacoes, analises_sem_data


def _analise_no_grupo(perfil, regra, analise):
    if not regra.so_quando_grupo:
        return True
    grupo = classificar(perfil, analise.situacao).id
    return grupo.casefold() in {valor.casefold() for valor in regra.so_quando_grupo}


def _resumo_prazo(avaliacoes):
    resumo = resumir_prazos(avaliacoes)
    return {
        "percentual": resumo.percentual_cumprido if resumo.base else None,
        "tem_dados": bool(resumo.base),
        "dentro": resumo.dentro,
        "fora": resumo.fora,
        "base": resumo.base,
        "atrasos_abertos": sum(
            avaliacao is not None and avaliacao.situacao == "aberto_atrasado"
            for avaliacao in avaliacoes
        ),
    }


def _feriados_prazo(prazos, documentos, hoje):
    extras = {feriado.data for feriado in prazos.feriados.extras}
    if not prazos.feriados.nacionais:
        return extras

    max_dias = max(
        (
            dias
            for regra in prazos.regras
            for dias in (regra.dias, *(excecao.dias for excecao in regra.excecoes))
        ),
        default=0,
    )
    datas_inicio = [hoje]
    for item in documentos:
        for emissao in item.documento.emissoes.all():
            datas_inicio.append(emissao.data_emissao)
            datas_inicio.extend(
                analise.data_analise
                for analise in emissao.analises.all()
                if analise.data_analise is not None
            )

    anos = set()
    dias_calendario = max_dias * 2 + 14
    for inicio in datas_inicio:
        ano_final = min(9999, (inicio + timedelta(days=dias_calendario)).year)
        anos.update(range(inicio.year, ano_final + 1))
    return extras.union(
        data for ano in anos for data in feriados_nacionais(ano)
    )


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


def _corresponde_filtros(documento, filtros, perfil=None):
    return all(
        (
            _id_categoria(perfil, documento)
            if perfil is not None and perfil.painel.categorias and nome == "categoria"
            else _valor_caixa(documento, nome)
        )
        in valores
        for nome, valores in filtros.items()
    )


def _id_categoria(perfil, documento):
    valores_caixas = {
        caixa.nome: _valor_caixa(documento, caixa.nome) for caixa in perfil.codigo.campos
    }
    categoria = classificar_categoria(perfil, valores_caixas)
    return categoria.id if categoria is not None else _ID_OUTROS


def _valor_recorte(perfil, documento, nome):
    if nome == "categoria" and perfil.painel.categorias:
        return _id_categoria(perfil, documento)
    return _valor_caixa(documento, nome)


def _rotulo_recorte(perfil, nome, valor, definicao_caixa):
    if nome == "categoria" and perfil.painel.categorias:
        if valor == _ID_OUTROS:
            return "Outros"
        return next(
            (categoria.rotulo for categoria in perfil.painel.categorias if categoria.id == valor),
            valor,
        )
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


def _valor_caixa(documento, nome):
    valor = documento.atributos.get(nome)
    if valor is None:
        valor = {"tipo": documento.tipo, "trecho": documento.trecho, "classe": documento.disciplina}.get(nome)
    return str(valor).strip() if valor is not None else ""


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
