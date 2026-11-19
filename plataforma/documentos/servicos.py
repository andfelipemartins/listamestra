from collections import defaultdict
from datetime import date, datetime, time

from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import F, Prefetch
from django.http import Http404
from django.urls import reverse
from django.utils import timezone

from acoes.models import AcaoPendencia
from acoes.services import contratos_acessiveis, resolver_contrato
from core.perfil import ErroPerfil, perfil_de_dict
from core.perfil.ciclo import _normalizar_situacao, rotulos_ciclo
from core.perfil.codigo import ErroCodigo, interpretar
from core.perfil.painel import classificar, classificar_categoria
from contratos.models import PerfilContrato
from painel.prazos import (
    _itens_avaliados_da_regra,
    dias_ate_vencimento,
    feriados_prazo,
)
from registro.servicos import carregar_eventos

from .models import Analise, CodigoDocumento, Documento, Emissao
from importacoes.models import PrevisaoEmissao


TAMANHO_PAGINA = 50


class DocumentosIndisponiveis(ValueError):
    pass


def carregar_lista_documentos(
    usuario,
    contrato_id=None,
    *,
    busca="",
    filtros_caixas=None,
    categoria="",
    situacao="",
    pagina=1,
):
    contratos = list(contratos_acessiveis(usuario))
    contrato = resolver_contrato(usuario, contrato_id)
    if contrato is None:
        return {
            "contratos": contratos,
            "contrato": None,
            "pagina": Paginator([], TAMANHO_PAGINA).get_page(1),
            "filtros_caixas": [],
            "categorias": [],
            "situacoes": [],
            "busca": busca,
            "categoria_selecionada": "",
            "situacao_selecionada": "",
            "query_sem_pagina": "",
        }

    perfil_modelo, perfil = _perfil_vigente(contrato)
    documentos = _documentos_com_historico(contrato, perfil_modelo)
    valores_por_documento = {}
    linhas = []
    ids_categorias = set()
    ids_situacoes = set()
    ultima_movimentacao = _movimentacoes_por_documento(documentos)

    for documento in documentos:
        codigo, valores = _codigo_e_valores(documento, perfil, perfil_modelo.pk)
        emissao, analise, situacao_atual, grupo = _situacao_atual(documento, perfil)
        categoria_obj = classificar_categoria(perfil, valores)
        categoria_id = categoria_obj.id if categoria_obj else ""
        categoria_rotulo = categoria_obj.rotulo if categoria_obj else "—"
        ids_categorias.add(categoria_id)
        ids_situacoes.add(grupo.id)
        valores_por_documento[documento.pk] = valores
        linhas.append(
            {
                "documento": documento,
                "codigo": codigo,
                "titulo": documento.titulo or "(sem título)",
                "categoria": categoria_rotulo,
                "categoria_id": categoria_id,
                "situacao": situacao_atual,
                "situacao_grupo": grupo,
                "ultima_emissao": _rotulo_ultima_emissao(documento, perfil),
                "ultima_movimentacao": ultima_movimentacao.get(documento.pk),
                "valores_caixas": valores,
            }
        )

    selecoes_caixas = filtros_caixas or {}
    filtros_caixas = _opcoes_filtros_caixas(perfil, documentos, valores_por_documento)
    filtros_caixas_selecionados = {}
    for filtro in filtros_caixas:
        nome = filtro["nome"]
        opcoes = {opcao["valor"] for opcao in filtro["opcoes"]}
        selecionados = {
            str(valor)
            for valor in selecoes_caixas.get(nome, ())
            if str(valor) in opcoes
        }
        filtro["selecionados"] = selecionados
        filtros_caixas_selecionados[nome] = selecionados

    categorias = [
        {"valor": cat.id, "rotulo": cat.rotulo}
        for cat in perfil.painel.categorias
        if cat.id in ids_categorias
    ]
    if "" in ids_categorias:
        categorias.append({"valor": "__sem_categoria__", "rotulo": "Sem categoria"})
    categoria_selecionada = categoria if any(opcao["valor"] == categoria for opcao in categorias) else ""

    situacoes = [
        {"valor": grupo.id, "rotulo": grupo.rotulo}
        for grupo in perfil.painel.grupos
        if grupo.id in ids_situacoes
    ]
    for identificador in ("nao_mapeado", "ignorado"):
        if identificador in ids_situacoes:
            situacoes.append(
                {
                    "valor": identificador,
                    "rotulo": "NÃO MAPEADO" if identificador == "nao_mapeado" else "IGNORADO",
                }
            )
    situacao_selecionada = situacao if any(
        opcao["valor"] == situacao for opcao in situacoes
    ) else ""

    termo = (busca or "").strip().casefold()
    linhas_filtradas = []
    for linha in linhas:
        documento = linha["documento"]
        if termo and termo not in linha["codigo"].casefold() and termo not in (documento.titulo or "").casefold():
            continue
        if categoria_selecionada not in ("", "__sem_categoria__") and linha["categoria_id"] != categoria_selecionada:
            continue
        if categoria_selecionada == "__sem_categoria__" and linha["categoria_id"]:
            continue
        if situacao_selecionada and linha["situacao_grupo"].id != situacao_selecionada:
            continue
        if any(
            selecionados
            and linha["valores_caixas"].get(nome, "") not in selecionados
            for nome, selecionados in filtros_caixas_selecionados.items()
        ):
            continue
        linhas_filtradas.append(linha)

    linhas_filtradas.sort(key=lambda linha: (linha["codigo"].casefold(), linha["documento"].pk))
    pagina_obj = Paginator(linhas_filtradas, TAMANHO_PAGINA).get_page(pagina)
    return {
        "contratos": contratos,
        "contrato": contrato,
        "perfil": perfil,
        "pagina": pagina_obj,
        "total_filtrado": len(linhas_filtradas),
        "filtros_caixas": filtros_caixas,
        "categorias": categorias,
        "situacoes": situacoes,
        "busca": busca,
        "categoria_selecionada": categoria_selecionada,
        "situacao_selecionada": situacao_selecionada,
    }


def carregar_pasta_documento(usuario, contrato_id, documento_id, *, hoje=None):
    contrato = resolver_contrato(usuario, contrato_id)
    if contrato is None:
        raise PermissionDenied("Você não participa deste contrato.")
    perfil_modelo, perfil = _perfil_vigente(contrato, hoje=hoje)
    documentos = _documentos_com_historico(contrato, perfil_modelo).filter(pk=documento_id)
    documento = documentos.first()
    if documento is None:
        raise Http404

    codigo, valores = _codigo_e_valores(documento, perfil, perfil_modelo.pk)
    partes_codigo = []
    for caixa in perfil.codigo.campos:
        valor = valores.get(caixa.nome, "")
        rotulo_valor = (caixa.valores or {}).get(valor, valor)
        partes_codigo.append(
            {"rotulo": caixa.rotulo, "valor": valor or "—", "significado": rotulo_valor or "—"}
        )

    emissao_atual, analise_atual, situacao_atual, grupo_atual = _situacao_atual(documento, perfil)
    categoria_obj = classificar_categoria(perfil, valores)
    previsao = (
        PrevisaoEmissao.objects.filter(contrato=contrato, documento=documento)
        .select_related("importacao")
        .order_by("-importacao__importado_em", "-pk")
        .first()
    )
    hoje = hoje or timezone.localdate()
    linha_tempo = _linha_tempo(perfil, documento, hoje)
    atividades = _atividades_documento(contrato, documento, codigo)
    return {
        "contrato": contrato,
        "perfil": perfil,
        "documento": documento,
        "codigo": codigo,
        "partes_codigo": partes_codigo,
        "categoria": categoria_obj.rotulo if categoria_obj else "—",
        "situacao": situacao_atual,
        "situacao_grupo": grupo_atual,
        "data_situacao": _data_analise(analise_atual) if analise_atual else None,
        "previsao": previsao,
        "linha_tempo": linha_tempo,
        "atividades": atividades,
        "url_lista": f"{reverse('documentos_lista')}?contrato={contrato.pk}",
    }


def _perfil_vigente(contrato, *, hoje=None):
    perfil_modelo = PerfilContrato.perfil_vigente(contrato, hoje or timezone.localdate())
    if perfil_modelo is None:
        raise DocumentosIndisponiveis("Este contrato ainda não tem um perfil vigente.")
    try:
        return perfil_modelo, perfil_de_dict(perfil_modelo.definicao)
    except ErroPerfil as erro:
        raise DocumentosIndisponiveis(f"O perfil vigente não pode alimentar os documentos: {erro}") from erro


def _documentos_com_historico(contrato, perfil_modelo):
    analises = Analise.objects.order_by(
        F("data_analise").desc(nulls_last=True), "-registrado_em", "-pk"
    )
    emissoes = Emissao.objects.order_by("data_emissao", "pk").prefetch_related(
        Prefetch("analises", queryset=analises)
    )
    codigos = CodigoDocumento.objects.filter(perfil=perfil_modelo).select_related("perfil")
    return (
        Documento.objects.filter(contrato=contrato)
        .select_related("contrato")
        .prefetch_related(
            Prefetch("emissoes", queryset=emissoes),
            Prefetch("codigos", queryset=codigos),
        )
        .order_by("identificador_base", "pk")
    )


def _codigo_e_valores(documento, perfil, perfil_id):
    codigo_obj = next((codigo for codigo in documento.codigos.all() if codigo.perfil_id == perfil_id), None)
    codigo = codigo_obj.codigo if codigo_obj else documento.identificador_base
    valores = {
        str(nome): str(valor).strip()
        for nome, valor in (documento.atributos or {}).items()
        if valor is not None and str(valor).strip()
    }
    interpretado = interpretar(perfil, codigo)
    if not isinstance(interpretado, ErroCodigo):
        valores.update(interpretado.segmentos)
    return codigo, valores


def _situacao_atual(documento, perfil):
    emissoes = list(documento.emissoes.all())
    if not emissoes:
        return None, None, None, classificar(perfil, None)
    movimentos = [
        (_datetime_da_data(emissao.data_emissao), 0, emissao.pk, emissao, None)
        for emissao in emissoes
    ]
    for emissao in emissoes:
        for analise in emissao.analises.all():
            data_efetiva = _data_analise(analise)
            instante = (
                _datetime_da_data(data_efetiva)
                if data_efetiva
                else analise.registrado_em or _datetime_da_data(emissao.data_emissao)
            )
            movimentos.append((instante, 1, analise.pk, emissao, analise))
    _, _, _, emissao, analise = max(movimentos, key=lambda item: item[:3])
    situacao = analise.situacao if analise else perfil.analise.inicial
    return emissao, analise, situacao, classificar(perfil, situacao)


def _rotulo_ultima_emissao(documento, perfil):
    emissoes = sorted(documento.emissoes.all(), key=lambda item: (item.data_emissao, item.pk))
    rotulos = rotulos_ciclo(perfil, emissoes)
    return rotulos[-1] if rotulos else "—"


def _opcoes_filtros_caixas(perfil, documentos, valores_por_documento):
    filtros = []
    for caixa in perfil.codigo.campos:
        valores = {
            valores_por_documento[documento.pk].get(caixa.nome, "")
            for documento in documentos
        }
        valores.discard("")
        if not valores:
            continue
        filtros.append(
            {
                "nome": caixa.nome,
                "rotulo": caixa.rotulo,
                "opcoes": [
                    {
                        "valor": valor,
                        "rotulo": f"{valor} — {(caixa.valores or {}).get(valor, valor)}",
                    }
                    for valor in sorted(valores, key=str.casefold)
                ],
            }
        )
    return filtros


def _movimentacoes_por_documento(documentos):
    ids = [documento.pk for documento in documentos]
    movimentacoes = defaultdict(list)
    for documento in documentos:
        movimentacoes[documento.pk].append(documento.criado_em)
        for emissao in documento.emissoes.all():
            movimentacoes[documento.pk].append(_datetime_da_data(emissao.data_emissao))
            for analise in emissao.analises.all():
                movimentacoes[documento.pk].append(
                    _datetime_da_data(analise.data_analise) if analise.data_analise else analise.registrado_em
                )
    for documento_id, data_hora in Documento.history.filter(id__in=ids).values_list(
        "id", "history_date"
    ):
        movimentacoes[documento_id].append(data_hora)
    for acao in AcaoPendencia.objects.filter(documento_id__in=ids).only(
        "documento_id", "criado_em", "resolvida_em"
    ):
        movimentacoes[acao.documento_id].append(acao.criado_em)
        if acao.resolvida_em:
            movimentacoes[acao.documento_id].append(acao.resolvida_em)
    return {
        documento_id: max(datas)
        for documento_id, datas in movimentacoes.items()
        if datas
    }


def _linha_tempo(perfil, documento, hoje):
    emissoes = sorted(documento.emissoes.all(), key=lambda item: (item.data_emissao, item.pk))
    rotulos = rotulos_ciclo(perfil, emissoes)
    aprovacoes = _situacoes_aprovacao(perfil)
    primeiro_aprovado = None
    analises_por_emissao = {}
    for emissao in emissoes:
        analises = sorted(emissao.analises.all(), key=_chave_analise)
        analises_por_emissao[emissao.pk] = analises
        for analise in analises:
            if _normalizar_situacao(analise.situacao) in aprovacoes:
                candidato = (_chave_analise(analise), analise.pk)
                if primeiro_aprovado is None or candidato < primeiro_aprovado[0]:
                    primeiro_aprovado = (candidato, analise.pk)

    prazos_por_emissao = defaultdict(list)
    feriados = set()
    if perfil.prazos:
        feriados = feriados_prazo(perfil.prazos, [documento], hoje)
        for regra in perfil.prazos.regras:
            registros, _ = _itens_avaliados_da_regra(perfil, regra, documento, hoje, feriados)
            for registro in registros:
                prazos_por_emissao[registro.emissao.pk].append(
                    _apresentar_prazo(registro, regra, hoje, feriados)
                )

    itens = []
    for indice, emissao in enumerate(emissoes):
        analises = []
        for analise in analises_por_emissao[emissao.pk]:
            analises.append(
                {
                    "objeto": analise,
                    "situacao": analise.situacao,
                    "etapa": analise.etapa,
                    "data": _data_analise(analise),
                    "data_registro": analise.registrado_em,
                    "origem": analise.origem,
                    "origem_rotulo": _rotulo_origem_analise(analise),
                    "aprovacao_que_conta": analise.pk == (primeiro_aprovado[1] if primeiro_aprovado else None),
                }
            )
        itens.append(
            {
                "emissao": emissao,
                "rotulo": rotulos[indice],
                "analises": analises,
                "prazos": sorted(prazos_por_emissao[emissao.pk], key=lambda item: item["regra"].rotulo.casefold()),
            }
        )
    return itens


def _situacoes_aprovacao(perfil):
    return {
        _normalizar_situacao(situacao)
        for situacao, transicao in perfil.analise.transicoes.items()
        if transicao.acao == "emitir_original"
    }


def _apresentar_prazo(registro, regra, hoje, feriados):
    avaliacao = registro.avaliacao
    if avaliacao.situacao == "no_prazo":
        status = "No prazo"
    elif avaliacao.situacao == "atrasado":
        status = f"Atrasado · {avaliacao.dias_atraso} dia(s)"
    elif avaliacao.situacao == "aberto_atrasado":
        status = f"Atrasado há {avaliacao.dias_atraso} dia(s)"
    else:
        dias = dias_ate_vencimento(regra, hoje, avaliacao.vencimento, feriados)
        status = "No prazo · vence hoje" if dias == 0 else f"No prazo · vence em {dias} dia(s)"
    return {
        "regra": regra,
        "status": status,
        "vencimento": avaliacao.vencimento,
        "inicio": registro.inicio,
        "fim": registro.fim,
    }


def _atividades_documento(contrato, documento, codigo):
    atividades = []
    for acao in (
        AcaoPendencia.objects.filter(contrato=contrato, documento=documento)
        .select_related("usuario")
        .order_by("criado_em", "pk")
    ):
        atividades.append(
            {
                "data_hora": acao.criado_em,
                "tipo": "ação",
                "titulo": acao.get_acao_display(),
                "resumo": acao.motivo or acao.tipo_pendencia,
                "usuario": _nome_usuario(acao.usuario),
                "resolvida_em": acao.resolvida_em,
            }
        )

    codigo_base = documento.identificador_base
    for evento in carregar_eventos(contrato):
        codigos = evento.get("codigos") or ()
        if isinstance(codigos, str):
            codigos = [valor.strip() for valor in codigos.split(",")]
        codigo_evento = evento.get("codigo") or ""
        if codigo_base not in codigos and codigo_base not in {
            valor.strip() for valor in codigo_evento.split(",")
        } and codigo not in codigos and codigo not in {
            valor.strip() for valor in codigo_evento.split(",")
        }:
            continue
        atividades.append(
            {
                "data_hora": evento["data_hora"],
                "tipo": "atividade",
                "titulo": evento.get("entidade", "Atividade"),
                "resumo": evento.get("resumo", ""),
                "usuario": evento.get("usuario_nome", "Sistema"),
                "resolvida_em": None,
            }
        )
    return sorted(atividades, key=lambda item: (item["data_hora"], item["tipo"], item["titulo"].casefold()))


def _chave_analise(analise):
    registrado = analise.registrado_em or timezone.now()
    data = _data_analise(analise)
    instante = _datetime_da_data(data) if data else registrado
    return instante, registrado, analise.pk


def _data_analise(analise):
    if analise.data_analise:
        return analise.data_analise
    if analise.registrado_em and analise.origem == Analise.Origem.DEDUZIDO_PW:
        return timezone.localtime(analise.registrado_em).date()
    return None


def _rotulo_origem_analise(analise):
    if analise.origem == Analise.Origem.DEDUZIDO_PW:
        return "Data deduzida" if analise.data_analise else "Data estimada pelo registro"
    return "Data explícita" if analise.data_analise else "Sem data informada"


def _datetime_da_data(valor):
    resultado = datetime.combine(valor, time.min)
    return timezone.make_aware(resultado, timezone.get_current_timezone())


def _nome_usuario(usuario):
    return usuario.get_full_name() or usuario.get_username() if usuario else "Sistema"
