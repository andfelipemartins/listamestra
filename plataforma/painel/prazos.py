"""Cálculos compartilhados de prazos e cronograma do contrato."""

from dataclasses import dataclass
from datetime import date, timedelta

from django.utils import timezone

from core.perfil.feriados import feriados_acervo, feriados_nacionais
from core.perfil.painel import classificar
from core.perfil.prazos import (
    avaliar as avaliar_prazo,
    contar_atrasos_por_faixa,
    indicador as resumir_prazos,
)
from documentos.models import Analise
from importacoes.cronograma import comparar_previsoes_cronograma
from importacoes.models import PrevisaoEmissao


_CORES_FAIXAS_ATRASO = (
    "var(--success-border)",
    "var(--warning-border)",
    "var(--indicador-alerta)",
    "var(--danger-border)",
)


@dataclass(frozen=True)
class ItemPrazo:
    emissao: object
    inicio: date
    fim: date | None
    analise: object | None
    avaliacao: object


def calcular_indicador_cronograma(
    contrato, perfil, documentos, caixa_selecionada, definicao_caixa, hoje,
    *, valor_recorte, rotulo_recorte,
):
    if not PrevisaoEmissao.objects.filter(contrato=contrato).exists():
        return None

    documentos_por_id = {item.documento.pk: item.documento for item in documentos}
    resultados = comparar_previsoes_cronograma(contrato, hoje=hoje)
    recortes = {}
    for documento in documentos_por_id.values():
        valor = valor_recorte(perfil, documento, caixa_selecionada) or "(sem informação)"
        recortes.setdefault(
            valor,
            {
                "valor": valor,
                "rotulo": rotulo_recorte(
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
        valor = valor_recorte(perfil, documento, caixa_selecionada) or "(sem informação)"
        recortes[valor][chave] += 1
        recortes[valor]["previstos"] += 1

    base = contagens["no_prazo"] + contagens["atrasados"] + contagens["vencidos_sem_emissao"]
    meta_percentual = perfil.prazos.meta_cronograma if perfil.prazos is not None else None
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


def calcular_indicadores_prazo(
    perfil, documentos, caixa_selecionada, definicao_caixa, hoje,
    *, valor_recorte, rotulo_recorte,
):
    prazos = perfil.prazos
    if prazos is None or not prazos.regras:
        return [], 0

    feriados = feriados_prazo(prazos, documentos, hoje)
    indicadores = []
    analises_sem_data = set()
    recortes_documentos = {}
    for item in documentos:
        valor = valor_recorte(perfil, item.documento, caixa_selecionada) or "(sem informação)"
        rotulo = rotulo_recorte(perfil, caixa_selecionada, valor, definicao_caixa)
        recortes_documentos.setdefault(valor, rotulo)

    for regra in prazos.regras:
        avaliacoes = []
        por_recorte = {valor: [] for valor in recortes_documentos}
        for item in documentos:
            registro, sem_data = _itens_avaliados_da_regra(
                perfil, regra, item.documento, hoje, feriados
            )
            analises_sem_data.update(sem_data)
            valor = valor_recorte(perfil, item.documento, caixa_selecionada) or "(sem informação)"
            for registro_prazo in registro:
                avaliacoes.append(registro_prazo.avaliacao)
                por_recorte[valor].append(registro_prazo.avaliacao)

        faixas_atraso = (
            regra.faixas_atraso
            if regra.faixas_atraso is not None
            else prazos.faixas_atraso
        )
        geral = _resumo_prazo(avaliacoes, faixas_atraso)
        recortes = []
        for valor, rotulo in sorted(
            recortes_documentos.items(), key=lambda item: item[1].casefold()
        ):
            resumo = _resumo_prazo(por_recorte[valor], faixas_atraso)
            recortes.append({"valor": valor, "rotulo": rotulo, **resumo})
        indicadores.append(
            {
                "regra": regra,
                **geral,
                "meta_percentual": regra.meta_percentual,
                "recortes": recortes,
            }
        )

    return indicadores, len(analises_sem_data)


def emissoes_abertas_prazo(perfil, regra, documento, hoje=None, feriados=None):
    """Retorna emissões abertas elegíveis para uma regra do perfil."""
    hoje = hoje or timezone.localdate()
    feriados = feriados if feriados is not None else feriados_prazo(perfil.prazos, [documento], hoje)
    registros, _ = _itens_avaliados_da_regra(perfil, regra, documento, hoje, feriados)
    return [
        registro
        for registro in registros
        if registro.avaliacao.situacao in {"aberto_no_prazo", "aberto_atrasado"}
    ]


def dias_ate_vencimento(regra, hoje, vencimento, feriados=()):
    """Conta os dias restantes na unidade definida pela regra do perfil."""
    if vencimento <= hoje:
        return 0
    if regra.tipo_dia == "corridos":
        return (vencimento - hoje).days
    feriados = set(feriados)
    dias = 0
    atual = hoje
    while atual < vencimento:
        atual += timedelta(days=1)
        if atual.weekday() < 5 and atual not in feriados:
            dias += 1
    return dias


def _itens_avaliados_da_regra(perfil, regra, documento, hoje, feriados):
    emissoes = sorted(
        documento.emissoes.all(), key=lambda emissao: (emissao.data_emissao, emissao.pk)
    )
    analises_sem_data = set()
    registros = []
    sigla = _valor_caixa(documento, "tipo") or documento.tipo

    if regra.inicio == "emissao" and regra.fim == "analise":
        for emissao in emissoes:
            analises = list(emissao.analises.all())
            elegiveis = [analise for analise in analises if _analise_no_grupo(perfil, regra, analise)]
            analises_sem_data.update(
                analise.pk
                for analise in elegiveis
                if analise.origem == Analise.Origem.DEDUZIDO_PW and analise.data_analise is None
            )
            datadas = [analise for analise in elegiveis if analise.data_analise is not None]
            if datadas:
                analise_final = max(datadas, key=lambda analise: (analise.data_analise, analise.pk))
                data_fim = analise_final.data_analise
                grupo = classificar(perfil, analise_final.situacao).id
            elif not analises and not regra.so_quando_grupo:
                analise_final = None
                data_fim = None
                grupo = None
            else:
                continue
            avaliacao = avaliar_prazo(
                regra, emissao.data_emissao, data_fim, hoje,
                sigla=sigla, grupo=grupo, feriados=feriados,
            )
            if avaliacao is not None:
                registros.append(ItemPrazo(emissao, emissao.data_emissao, data_fim, analise_final, avaliacao))

    elif regra.inicio == "analise" and regra.fim == "proxima_emissao":
        for indice, emissao in enumerate(emissoes):
            analises = [
                analise for analise in emissao.analises.all()
                if _analise_no_grupo(perfil, regra, analise)
            ]
            analises_sem_data.update(
                analise.pk
                for analise in analises
                if analise.origem == Analise.Origem.DEDUZIDO_PW and analise.data_analise is None
            )
            datadas = [analise for analise in analises if analise.data_analise is not None]
            if not datadas:
                continue
            analise_revisao = max(datadas, key=lambda analise: (analise.data_analise, analise.pk))
            proxima_emissao = emissoes[indice + 1] if indice + 1 < len(emissoes) else None
            data_fim = proxima_emissao.data_emissao if proxima_emissao else None
            avaliacao = avaliar_prazo(
                regra, analise_revisao.data_analise, data_fim, hoje,
                sigla=sigla,
                grupo=classificar(perfil, analise_revisao.situacao).id,
                feriados=feriados,
            )
            if avaliacao is not None:
                registros.append(
                    ItemPrazo(emissao, analise_revisao.data_analise, data_fim, analise_revisao, avaliacao)
                )

    return registros, analises_sem_data


def _analise_no_grupo(perfil, regra, analise):
    if not regra.so_quando_grupo:
        return True
    grupo = classificar(perfil, analise.situacao).id
    return grupo.casefold() in {valor.casefold() for valor in regra.so_quando_grupo}


def _resumo_prazo(avaliacoes, faixas_atraso=None):
    avaliacoes = list(avaliacoes)
    resumo = resumir_prazos(avaliacoes)
    contagens_faixas = contar_atrasos_por_faixa(avaliacoes, faixas_atraso or ())
    base_faixas = sum(contagem.total for contagem in contagens_faixas)
    faixas_exibicao = []
    limite_anterior = 0
    for indice, contagem in enumerate(contagens_faixas):
        faixa = contagem.faixa
        if faixa.ate_dias is None:
            intervalo = (
                f"Mais de {limite_anterior} dias"
                if limite_anterior
                else "Qualquer atraso"
            )
        elif limite_anterior:
            intervalo = f"{limite_anterior + 1} a {faixa.ate_dias} dias"
        else:
            intervalo = f"Até {faixa.ate_dias} dias"
        if faixa.ate_dias is not None:
            limite_anterior = faixa.ate_dias
        faixas_exibicao.append(
            {
                "rotulo": faixa.rotulo,
                "ate_dias": faixa.ate_dias,
                "intervalo": intervalo,
                "entregues_com_atraso": contagem.entregues_com_atraso,
                "abertos_vencidos": contagem.abertos_vencidos,
                "total": contagem.total,
                "percentual": contagem.total * 100.0 / base_faixas if base_faixas else 0,
                "cor": _CORES_FAIXAS_ATRASO[min(indice, len(_CORES_FAIXAS_ATRASO) - 1)],
            }
        )
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
        "faixas_atraso": faixas_exibicao,
    }


def feriados_prazo(prazos, documentos, hoje):
    extras = {feriado.data for feriado in prazos.feriados.extras}
    max_dias = max(
        (dias for regra in prazos.regras for dias in (regra.dias, *(excecao.dias for excecao in regra.excecoes))),
        default=0,
    )
    datas_inicio = [hoje]
    for item in documentos:
        documento = getattr(item, "documento", item)
        for emissao in documento.emissoes.all():
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

    regionais = set()
    regiao = prazos.feriados.regiao
    if regiao is not None:
        from contratos.models import FeriadoAcervo

        try:
            regras_acervo = list(
                FeriadoAcervo.objects.filter(uf__iexact=regiao.uf).values(
                    "nome",
                    "abrangencia",
                    "uf",
                    "municipio",
                    "tipo_regra",
                    "dia",
                    "mes",
                    "deslocamento_pascoa",
                    "vigencia_de",
                    "vigencia_ate",
                )
            )
        except RuntimeError as erro:
            if not str(erro).startswith("Database access not allowed"):
                raise
            # Cálculos unitários sem banco continuam usando nacionais e extras do perfil.
            regras_acervo = []
        regionais.update(
            data
            for ano in anos
            for data in feriados_acervo(
                ano,
                regras_acervo,
                uf=regiao.uf,
                municipio=regiao.municipio,
            )
        )

    if not prazos.feriados.nacionais:
        return extras.union(regionais)
    nacionais = {data for ano in anos for data in feriados_nacionais(ano)}
    return extras.union(regionais, nacionais)


def _valor_caixa(documento, nome):
    valor = documento.atributos.get(nome)
    if valor is None:
        valor = {"tipo": documento.tipo, "trecho": documento.trecho, "classe": documento.disciplina}.get(nome)
    return str(valor).strip() if valor is not None else ""
