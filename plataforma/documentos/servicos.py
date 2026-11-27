from collections import defaultdict
from datetime import date, datetime, time
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, Prefetch
from django.http import Http404
from django.urls import reverse
from django.utils import timezone

from acoes.models import AcaoPendencia
from acoes.services import contratos_acessiveis, resolver_contrato
from contas.models import Usuario
from core.perfil import ErroPerfil, perfil_de_dict
from core.perfil.ciclo import _normalizar_situacao, rotulo_cronologico, rotulos_ciclo
from core.perfil.codigo import ErroCodigo, interpretar
from core.perfil.painel import classificar, classificar_categoria
from contratos.models import Participacao, PerfilContrato
from painel.servicos import _aplicar_cancelamento_sistema
from painel.prazos import (
    _itens_avaliados_da_regra,
    dias_ate_vencimento,
    feriados_prazo,
)
from registro.servicos import carregar_eventos

from .models import Analise, CodigoDocumento, Documento, Emissao
from importacoes.models import PrevisaoEmissao


TAMANHO_PAGINA = 50
TAMANHO_PAGINA_LISTA_MESTRA = 100


class DocumentosIndisponiveis(ValueError):
    pass


def carregar_lista_mestra(
    usuario,
    contrato_id=None,
    *,
    busca="",
    tipo="",
    disciplina="",
    fase="",
    situacao="",
    mostrar_cancelados=False,
    pagina=1,
):
    contratos = list(contratos_acessiveis(usuario))
    contrato = resolver_contrato(usuario, contrato_id)
    if contrato is None:
        pagina_obj = Paginator([], TAMANHO_PAGINA_LISTA_MESTRA).get_page(1)
        return {
            "contratos": contratos,
            "contrato": None,
            "pagina": pagina_obj,
            "total_filtrado": 0,
            "segmentos_codigo": [],
            "tipos": [],
            "disciplinas": [],
            "fases": [],
            "situacoes": [],
            "busca": busca,
            "tipo_selecionado": "",
            "disciplina_selecionada": "",
            "fase_selecionada": "",
            "situacao_selecionada": "",
            "mostrar_cancelados": bool(mostrar_cancelados),
        }

    perfil_modelo, perfil = _perfil_vigente(contrato)
    campos_codigo = [
        campo
        for campo in perfil.codigo.campos
        if campo.nome != perfil.codigo.segmento_revisao
    ]
    documentos = _documentos_com_historico(contrato, perfil_modelo)
    linhas = []
    for documento in documentos:
        if documento.cancelado_em and not mostrar_cancelados:
            continue
        codigo, valores = _codigo_e_valores(documento, perfil, perfil_modelo.pk)
        emissoes = sorted(
            documento.emissoes.all(),
            key=lambda emissao: (emissao.data_emissao, emissao.pk),
        )
        rotulos = rotulo_cronologico(emissoes)
        for emissao, rotulo in zip(emissoes, rotulos):
            analise = next(iter(emissao.analises.all()), None)
            tipo_documental = valores.get("tipo") or documento.tipo or ""
            disciplina_documento = documento.disciplina or valores.get("classe", "")
            linhas.append(
                {
                    "documento": documento,
                    "emissao": emissao,
                    "codigo": codigo,
                    "segmentos": [valores.get(campo.nome, "") for campo in campos_codigo],
                    "tipo": tipo_documental,
                    "disciplina": disciplina_documento,
                    "fase": emissao.fase,
                    "fase_rotulo": emissao.get_fase_display(),
                    "rotulo_cronologico": rotulo,
                    "analise": analise,
                    "situacao": (analise.situacao or "—") if analise else "Em análise",
                    "data_analise": analise.data_analise if analise else None,
                    "documento_retorno": analise.documento_retorno if analise else "",
                    "observacao": (
                        (analise.observacao or emissao.observacao)
                        if analise
                        else emissao.observacao
                    ),
                }
            )

    tipos = _opcoes_lista_mestra(linhas, "tipo")
    disciplinas = _opcoes_lista_mestra(linhas, "disciplina")
    fases = [
        {"valor": valor, "rotulo": rotulo}
        for valor, rotulo in Emissao.Fase.choices
        if any(linha["fase"] == valor for linha in linhas)
    ]
    situacoes = _opcoes_lista_mestra(linhas, "situacao")
    tipo_selecionado = _selecionar_opcao_lista_mestra(tipo, tipos)
    disciplina_selecionada = _selecionar_opcao_lista_mestra(disciplina, disciplinas)
    fase_selecionada = _selecionar_opcao_lista_mestra(fase, fases)
    situacao_selecionada = _selecionar_opcao_lista_mestra(situacao, situacoes)

    termo = (busca or "").strip().casefold()
    linhas_filtradas = [
        linha
        for linha in linhas
        if (not termo or termo in linha["codigo"].casefold() or termo in (linha["documento"].titulo or "").casefold())
        and (not tipo_selecionado or linha["tipo"] == tipo_selecionado)
        and (not disciplina_selecionada or linha["disciplina"] == disciplina_selecionada)
        and (not fase_selecionada or linha["fase"] == fase_selecionada)
        and (not situacao_selecionada or linha["situacao"] == situacao_selecionada)
    ]
    linhas_filtradas.sort(
        key=lambda linha: (
            linha["codigo"].casefold(),
            linha["emissao"].data_emissao,
            linha["emissao"].pk,
        )
    )
    pagina_obj = Paginator(linhas_filtradas, TAMANHO_PAGINA_LISTA_MESTRA).get_page(pagina)
    return {
        "contratos": contratos,
        "contrato": contrato,
        "perfil": perfil,
        "pagina": pagina_obj,
        "total_filtrado": len(linhas_filtradas),
        "segmentos_codigo": campos_codigo,
        "tipos": tipos,
        "disciplinas": disciplinas,
        "fases": fases,
        "situacoes": situacoes,
        "busca": busca,
        "tipo_selecionado": tipo_selecionado,
        "disciplina_selecionada": disciplina_selecionada,
        "fase_selecionada": fase_selecionada,
        "situacao_selecionada": situacao_selecionada,
        "mostrar_cancelados": bool(mostrar_cancelados),
    }


def _opcoes_lista_mestra(linhas, campo):
    valores = sorted(
        {linha[campo] for linha in linhas if linha[campo]},
        key=str.casefold,
    )
    return [{"valor": valor, "rotulo": valor} for valor in valores]


def _selecionar_opcao_lista_mestra(valor, opcoes):
    return valor if any(opcao["valor"] == valor for opcao in opcoes) else ""


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
            "pode_cancelar_documentos": False,
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
        _, _, _, grupo_pw = _situacao_sem_cancelamento_sistema(documento, perfil)
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
                "situacao_rotulo": (
                    "Cancelado"
                    if documento.cancelado_em or grupo.id.casefold() == "cancelado"
                    else grupo.rotulo
                ),
                "cancelado_sistema": bool(
                    documento.cancelado_em and grupo_pw.id.casefold() != "cancelado"
                ),
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
        "pode_cancelar_documentos": pode_cancelar_documentos(usuario, contrato),
    }


def carregar_confirmacao_cancelamento(usuario, contrato_id, ids_documentos):
    contrato = resolver_contrato(usuario, contrato_id)
    if contrato is None:
        raise PermissionDenied("Você não participa deste contrato.")
    if not pode_cancelar_documentos(usuario, contrato):
        raise PermissionDenied("Somente o administrador do contrato pode cancelar documentos.")

    ids = _normalizar_ids_documentos(ids_documentos)
    perfil_modelo, perfil = _perfil_vigente(contrato)
    documentos = list(
        Documento.objects.filter(pk__in=ids, contrato=contrato)
        .select_related("cancelado_por")
        .order_by("identificador_base", "pk")
    )
    if len(documentos) != len(ids):
        raise ValueError("Um ou mais documentos não pertencem a este contrato.")

    return {
        "contrato": contrato,
        "documentos_cancelamento": [
            {
                "documento": documento,
                "codigo": _codigo_e_valores(documento, perfil, perfil_modelo.pk)[0],
            }
            for documento in documentos
        ],
        "ids_cancelamento": ids,
        "motivos_cancelamento": perfil.cancelamento.motivos,
        "pode_cancelar_documentos": True,
    }


def cancelar_documentos(usuario, contrato, ids_documentos, motivo, observacao=""):
    if not pode_cancelar_documentos(usuario, contrato):
        raise PermissionDenied("Somente o administrador do contrato pode cancelar documentos.")

    ids = _normalizar_ids_documentos(ids_documentos)
    motivo = (motivo or "").strip()
    observacao = (observacao or "").strip()
    perfil_modelo, perfil = _perfil_vigente(contrato)
    motivo_configurado = next(
        (item for item in perfil.cancelamento.motivos if item.id == motivo),
        None,
    )
    if motivo_configurado is None:
        raise ValueError("Selecione um motivo da lista.")
    if motivo_configurado.exige_observacao and not observacao:
        raise ValueError("Informe a observação para este motivo.")
    if len(observacao) > 1000:
        raise ValueError("A observação deve ter no máximo 1000 caracteres.")

    lote = uuid4().hex
    agora = timezone.now()
    cancelados = []
    ignorados = []
    with transaction.atomic():
        documentos = list(
            Documento.objects.select_for_update()
            .filter(pk__in=ids)
            .prefetch_related(
                Prefetch(
                    "emissoes",
                    queryset=Emissao.objects.order_by("data_emissao", "pk").prefetch_related(
                        Prefetch(
                            "analises",
                            queryset=Analise.objects.order_by(
                                F("data_analise").desc(nulls_last=True),
                                "-registrado_em",
                                "-pk",
                            ),
                        )
                    ),
                )
            )
            .order_by("identificador_base", "pk")
        )
        if len(documentos) != len(ids) or any(
            documento.contrato_id != contrato.pk for documento in documentos
        ):
            raise ValueError("Um ou mais documentos não pertencem a este contrato.")

        for documento in documentos:
            codigo = _codigo_e_valores(documento, perfil, perfil_modelo.pk)[0]
            if documento.cancelado_em:
                ignorados.append({"codigo": codigo, "motivo": "já cancelado pelo sistema"})
                continue
            _, _, _, grupo = _situacao_atual(documento, perfil)
            if grupo.id.casefold() == "cancelado":
                ignorados.append({"codigo": codigo, "motivo": "já cancelado pelo PW"})
                continue

            documento.cancelado_em = agora
            documento.cancelado_por = usuario
            documento.motivo_cancelamento = motivo
            documento.motivo_cancelamento_obs = observacao
            documento._history_user = usuario
            documento._change_reason = f"cancelamento_sistema:{lote}"
            documento.save(
                update_fields=(
                    "cancelado_em",
                    "cancelado_por",
                    "motivo_cancelamento",
                    "motivo_cancelamento_obs",
                )
            )
            cancelados.append(codigo)

    return {
        "quantidade_cancelada": len(cancelados),
        "codigos_cancelados": tuple(cancelados),
        "ignorados": tuple(ignorados),
    }


def carregar_confirmacao_reativacao(usuario, contrato_id, ids_documentos):
    contrato = resolver_contrato(usuario, contrato_id)
    if contrato is None:
        raise PermissionDenied("Você não participa deste contrato.")
    if not pode_cancelar_documentos(usuario, contrato):
        raise PermissionDenied("Somente o administrador do contrato pode reativar documentos.")

    ids = _normalizar_ids_documentos(ids_documentos)
    perfil_modelo, perfil = _perfil_vigente(contrato)
    documentos = list(
        _documentos_com_historico(contrato, perfil_modelo)
        .filter(pk__in=ids)
        .order_by("identificador_base", "pk")
    )
    if len(documentos) != len(ids):
        raise ValueError("Um ou mais documentos não pertencem a este contrato.")

    itens = []
    for documento in documentos:
        _, _, _, grupo_pw = _situacao_sem_cancelamento_sistema(documento, perfil)
        cancelado_pw = grupo_pw.id.casefold() == "cancelado"
        reativavel = bool(documento.cancelado_em and not cancelado_pw)
        if cancelado_pw:
            aviso = "Só volta quando o PW mudar."
        elif not documento.cancelado_em:
            aviso = "Não está cancelado pelo sistema."
        else:
            aviso = ""
        itens.append(
            {
                "documento": documento,
                "codigo": _codigo_e_valores(documento, perfil, perfil_modelo.pk)[0],
                "reativavel": reativavel,
                "aviso": aviso,
            }
        )
    return {
        "contrato": contrato,
        "documentos_reativacao": itens,
        "ids_reativacao": ids,
        "quantidade_reativavel": sum(item["reativavel"] for item in itens),
        "pode_cancelar_documentos": True,
    }


def reativar_documentos(usuario, contrato, ids_documentos, observacao):
    if not pode_cancelar_documentos(usuario, contrato):
        raise PermissionDenied("Somente o administrador do contrato pode reativar documentos.")

    ids = _normalizar_ids_documentos(ids_documentos)
    observacao = (observacao or "").strip()
    if not observacao:
        raise ValueError("Informe o motivo da reativação.")
    if len(observacao) > 1000:
        raise ValueError("A observação deve ter no máximo 1000 caracteres.")

    perfil_modelo, perfil = _perfil_vigente(contrato)
    lote = uuid4().hex
    reativados = []
    ignorados = []
    with transaction.atomic():
        documentos = list(
            _documentos_com_historico(contrato, perfil_modelo)
            .select_for_update()
            .filter(pk__in=ids)
            .order_by("identificador_base", "pk")
        )
        if len(documentos) != len(ids):
            raise ValueError("Um ou mais documentos não pertencem a este contrato.")

        for documento in documentos:
            codigo = _codigo_e_valores(documento, perfil, perfil_modelo.pk)[0]
            _, _, _, grupo_pw = _situacao_sem_cancelamento_sistema(documento, perfil)
            if grupo_pw.id.casefold() == "cancelado":
                ignorados.append(
                    {"codigo": codigo, "motivo": "cancelado pelo PW; só volta quando o PW mudar"}
                )
                continue
            if not documento.cancelado_em:
                ignorados.append(
                    {"codigo": codigo, "motivo": "não cancelado pelo sistema"}
                )
                continue

            documento.cancelado_em = None
            documento.cancelado_por = None
            documento.motivo_cancelamento = ""
            documento.motivo_cancelamento_obs = ""
            documento.observacao_reativacao = observacao
            documento._history_user = usuario
            documento._change_reason = f"reativacao_sistema:{lote}"
            documento.save(
                update_fields=(
                    "cancelado_em",
                    "cancelado_por",
                    "motivo_cancelamento",
                    "motivo_cancelamento_obs",
                    "observacao_reativacao",
                )
            )
            reativados.append(codigo)

    return {
        "quantidade_reativada": len(reativados),
        "codigos_reativados": tuple(reativados),
        "ignorados": tuple(ignorados),
    }


def pode_cancelar_documentos(usuario, contrato):
    return bool(
        usuario.is_staff
        or Participacao.objects.filter(
            usuario=usuario,
            contrato=contrato,
            ativo=True,
            papel=Usuario.Perfil.ADMIN,
        ).exists()
    )


def _normalizar_ids_documentos(ids_documentos):
    if isinstance(ids_documentos, (str, int)):
        ids_documentos = [ids_documentos]
    try:
        ids = list(dict.fromkeys(int(valor) for valor in ids_documentos))
    except (TypeError, ValueError) as erro:
        raise ValueError("Selecione documentos válidos para cancelar.") from erro
    if not ids or any(valor <= 0 for valor in ids):
        raise ValueError("Selecione ao menos um documento para cancelar.")
    return ids


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
    pode_editar_motivo = _pode_editar_motivo_reabertura(usuario, contrato)
    _anotar_motivos_reabertura(perfil, documento, linha_tempo, pode_editar_motivo)
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
        "situacao_rotulo": (
            "Cancelado"
            if documento.cancelado_em or grupo_atual.id.casefold() == "cancelado"
            else grupo_atual.rotulo
        ),
        "data_situacao": _data_analise(analise_atual) if analise_atual else None,
        "cancelamento": (
            {
                "em": documento.cancelado_em,
                "por": _nome_usuario(documento.cancelado_por),
                "motivo": _rotulo_motivo_cancelamento(perfil, documento.motivo_cancelamento),
                "observacao": documento.motivo_cancelamento_obs,
            }
            if documento.cancelado_em
            else None
        ),
        "pode_cancelar_documentos": pode_cancelar_documentos(usuario, contrato),
        "pode_reativar_documentos": (
            pode_cancelar_documentos(usuario, contrato)
            and bool(documento.cancelado_em)
            and _situacao_sem_cancelamento_sistema(documento, perfil)[3].id.casefold()
            != "cancelado"
        ),
        "previsao": previsao,
        "linha_tempo": linha_tempo,
        "motivos_reabertura": [
            ("", "Não informado"),
            *Emissao.MotivoReabertura.choices,
        ],
        "atividades": atividades,
        "url_lista": f"{reverse('documentos_lista')}?contrato={contrato.pk}",
    }


def atualizar_motivo_reabertura(
    usuario,
    contrato_id,
    documento_id,
    emissao_id,
    motivo,
    observacao="",
):
    contrato = resolver_contrato(usuario, contrato_id)
    if contrato is None:
        raise PermissionDenied("Você não participa deste contrato.")
    if not _pode_editar_motivo_reabertura(usuario, contrato):
        raise PermissionDenied("Seu papel neste contrato permite apenas visualizar.")

    try:
        emissao_id = int(emissao_id)
    except (TypeError, ValueError) as erro:
        raise ValueError("Selecione uma emissão de reabertura válida.") from erro
    emissao = (
        Emissao.objects.select_related("documento")
        .filter(pk=emissao_id, documento_id=documento_id, documento__contrato=contrato)
        .first()
    )
    if emissao is None:
        raise Http404

    motivo = (motivo or "").strip()
    observacao = (observacao or "").strip()
    motivos_validos = {valor for valor, _ in Emissao.MotivoReabertura.choices}
    if motivo not in motivos_validos:
        raise ValueError("Selecione um motivo da lista.")
    if observacao and motivo != Emissao.MotivoReabertura.OUTRO:
        raise ValueError("A observação só pode ser preenchida para o motivo Outro.")
    if len(observacao) > 300:
        raise ValueError("A observação deve ter no máximo 300 caracteres.")
    if not _emissao_eh_primeira_reabertura(emissao):
        raise ValueError("O motivo só pode ser alterado na primeira emissão de uma reabertura.")

    emissao.motivo_reabertura = motivo
    emissao.motivo_reabertura_obs = observacao
    try:
        emissao.full_clean()
    except ValidationError as erro:
        raise ValueError(" ".join(erro.messages)) from erro
    emissao._history_user = usuario
    emissao.save(update_fields=("motivo_reabertura", "motivo_reabertura_obs"))
    return emissao


def listar_reaberturas_do_contrato(contrato, *, hoje=None):
    """Lista reaberturas deduzidas do perfil, sem alterar emissões ou documentos."""
    _, perfil = _perfil_vigente(contrato, hoje=hoje)
    documentos = (
        Documento.objects.filter(contrato=contrato)
        .prefetch_related("emissoes")
        .order_by("identificador_base", "pk")
    )
    resultado = []
    for documento in documentos:
        emissoes = sorted(documento.emissoes.all(), key=lambda item: (item.data_emissao, item.pk))
        for grupo in _grupos_reabertura(perfil, emissoes):
            primeira = grupo["emissoes"][0]
            motivo = primeira.motivo_reabertura or ""
            resultado.append(
                {
                    "documento": documento,
                    "serie": grupo["serie"],
                    "revisoes": tuple(dict.fromkeys(item.revisao for item in grupo["emissoes"])),
                    "motivo": motivo,
                    "motivo_rotulo": _rotulo_motivo_reabertura(motivo),
                    "motivo_obs": primeira.motivo_reabertura_obs or "",
                }
            )
    return resultado


def _pode_editar_motivo_reabertura(usuario, contrato):
    return bool(
        usuario.is_staff
        or Participacao.objects.filter(
            usuario=usuario,
            contrato=contrato,
            ativo=True,
            papel__in=(Usuario.Perfil.ADMIN, Usuario.Perfil.EQUIPE),
        ).exists()
    )


def _emissao_eh_primeira_reabertura(emissao):
    if not emissao.documento_id or not emissao.data_emissao:
        return False
    documento = emissao.documento
    perfil_modelo = PerfilContrato.perfil_vigente(documento.contrato, emissao.data_emissao)
    if perfil_modelo is None:
        return False
    try:
        perfil = perfil_de_dict(perfil_modelo.definicao)
    except ErroPerfil:
        return False

    emissoes = list(
        Emissao.objects.filter(documento_id=documento.pk)
        .exclude(pk=emissao.pk)
        .order_by("data_emissao", "pk")
    )
    emissoes.append(emissao)
    emissoes.sort(
        key=lambda item: (
            item.data_emissao,
            item.pk if item.pk is not None else float("inf"),
        )
    )
    return any(
        grupo["emissoes"][0] is emissao
        for grupo in _grupos_reabertura(perfil, emissoes)
    )


def _grupos_reabertura(perfil, emissoes):
    grupos = []
    grupo_atual = None
    for emissao, rotulo in zip(emissoes, rotulos_ciclo(perfil, emissoes)):
        if not rotulo.startswith("Reabertura"):
            grupo_atual = None
            continue
        prefixo = rotulo.partition(" · ")[0]
        serie = prefixo.removeprefix("Reabertura ").strip() or "Reabertura"
        if grupo_atual is None or grupo_atual["serie"] != serie:
            grupo_atual = {"serie": serie, "emissoes": []}
            grupos.append(grupo_atual)
        grupo_atual["emissoes"].append(emissao)
    return grupos


def _anotar_motivos_reabertura(perfil, documento, linha_tempo, pode_editar):
    emissoes = sorted(documento.emissoes.all(), key=lambda item: (item.data_emissao, item.pk))
    por_emissao = {}
    for grupo in _grupos_reabertura(perfil, emissoes):
        primeira = grupo["emissoes"][0]
        motivo = primeira.motivo_reabertura or ""
        dados = {
            "serie": grupo["serie"],
            "motivo": motivo,
            "motivo_rotulo": _rotulo_motivo_reabertura(motivo),
            "motivo_obs": primeira.motivo_reabertura_obs or "",
            "emissao_motivo_id": primeira.pk,
            "motivo_editavel": pode_editar and primeira.pk is not None,
        }
        for emissao in grupo["emissoes"]:
            por_emissao[emissao.pk] = {
                **dados,
                "motivo_editavel": pode_editar and emissao.pk == primeira.pk,
            }

    for item in linha_tempo:
        dados = por_emissao.get(item["emissao"].pk)
        if dados:
            item.update(dados)


def _rotulo_motivo_reabertura(motivo):
    return dict(Emissao.MotivoReabertura.choices).get(motivo, "Não informado")


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
        .select_related("contrato", "cancelado_por")
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
        situacao, _ = _aplicar_cancelamento_sistema(documento, perfil, None)
        return None, None, situacao, classificar(perfil, situacao)
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
    situacao, _ = _aplicar_cancelamento_sistema(documento, perfil, situacao)
    return emissao, analise, situacao, classificar(perfil, situacao)


def _situacao_sem_cancelamento_sistema(documento, perfil):
    cancelado_em = documento.cancelado_em
    documento.cancelado_em = None
    try:
        return _situacao_atual(documento, perfil)
    finally:
        documento.cancelado_em = cancelado_em


def _rotulo_motivo_cancelamento(perfil, identificador):
    return next(
        (motivo.rotulo for motivo in perfil.cancelamento.motivos if motivo.id == identificador),
        identificador,
    )


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
