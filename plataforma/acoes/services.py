from collections import defaultdict
from datetime import date, timedelta
from urllib.parse import urlencode

from django.core.exceptions import PermissionDenied
from django.db.models import Count, F, Prefetch
from django.urls import reverse
from django.utils import timezone

from core.perfil import ErroPerfil, escopo_do_documento, perfil_de_dict
from core.perfil.codigo import ErroCodigo, interpretar
from core.perfil.painel import classificar, classificar_categoria
from contas.models import Usuario
from contratos.models import Contrato, Participacao, PerfilContrato
from documentos.models import Analise, Documento, Emissao
from importacoes.cronograma import comparar_previsoes_cronograma
from importacoes.models import (
    ImportacaoID,
    ImportacaoSituacao,
    InconsistenciaImportacao,
    IndiceDocumentos,
    ItemPrevisto,
    PrevisaoEmissao,
)
from painel.prazos import dias_ate_vencimento, emissoes_abertas_prazo, feriados_prazo
from backups.services import alerta_backup_para_usuario

from .models import AcaoPendencia


PRAZO_ANALISE = "analise-cliente"
PRAZO_DEVOLUCAO = "devolucao"
CLASSES_SEM_ESCOPO = "classes-sem-escopo"
JANELA_TITULO_DIFERENTE_ID = "titulo-diferente-id"
TIPOS_JANELA = {
    "erros": "Erros a corrigir",
    PRAZO_ANALISE: "Análise do cliente",
    PRAZO_DEVOLUCAO: "Nossa devolução",
    "cronograma": "Cronograma",
    "recusadas": "Linhas recusadas abertas",
    CLASSES_SEM_ESCOPO: "Classe sem escopo",
    JANELA_TITULO_DIFERENTE_ID: "Título diferente do ID",
}
_DIAS_CRONOGRAMA = 7
PENDENCIA_FALTA_NO_PW = "falta_no_pw"
PENDENCIA_FALTA_NO_NOSSO_ID = "falta_no_nosso_id"
PENDENCIA_TITULO_DIFERENTE_ID = "titulo_diferente_id"
_PENDENCIAS_ID = {PENDENCIA_FALTA_NO_PW, PENDENCIA_FALTA_NO_NOSSO_ID}
_TEXTOS_RESUMO = {
    "erros": "documentos com erros a corrigir",
    PRAZO_ANALISE: "documentos aguardando análise do cliente",
    PRAZO_DEVOLUCAO: "documentos aguardando nossa devolução",
    "cronograma": "emissões vencidas ou próximas",
    "recusadas": "linhas recusadas nas importações",
    CLASSES_SEM_ESCOPO: "documentos agrupados por classe sem escopo ligado no perfil",
    JANELA_TITULO_DIFERENTE_ID: "documentos com título diferente do ID",
}


def contratos_acessiveis(usuario):
    contratos = Contrato.objects.all()
    if not usuario.is_staff:
        contratos = contratos.filter(
            ativo=True,
            participacoes__usuario=usuario,
            participacoes__ativo=True,
        )
    return contratos.distinct().order_by("nome", "pk")


def contratos_para_selecao(usuario):
    """Lista contratos ativos disponíveis para a pessoa, com papel e contagem."""
    if usuario.is_staff:
        contratos = list(
            Contrato.objects.filter(ativo=True)
            .annotate(total_documentos=Count("documentos", distinct=True))
            .order_by("nome", "pk")
        )
        papeis = {
            participacao.contrato_id: participacao.get_papel_display()
            for participacao in Participacao.objects.filter(
                usuario=usuario,
                ativo=True,
                contrato__in=contratos,
            )
        }
        return [
            {
                "contrato": contrato,
                "papel": papeis.get(contrato.pk, "Acesso administrativo"),
                "total_documentos": contrato.total_documentos,
            }
            for contrato in contratos
        ]

    participacoes = (
        Participacao.objects.filter(
            usuario=usuario,
            ativo=True,
            contrato__ativo=True,
        )
        .select_related("contrato")
        .annotate(total_documentos=Count("contrato__documentos", distinct=True))
        .order_by("contrato__nome", "contrato_id")
    )
    return [
        {
            "contrato": participacao.contrato,
            "papel": participacao.get_papel_display(),
            "total_documentos": participacao.total_documentos,
        }
        for participacao in participacoes
    ]


def resolver_contrato(usuario, contrato_id=None):
    contratos = contratos_acessiveis(usuario)
    if contrato_id in (None, ""):
        return contratos.first()
    try:
        contrato = contratos.filter(pk=int(contrato_id)).first()
    except (TypeError, ValueError):
        contrato = None
    if contrato is None:
        raise PermissionDenied("Você não participa deste contrato.")
    return contrato


def _pode_editar_perfil(usuario, contrato):
    return usuario.is_staff or Participacao.objects.filter(
        usuario=usuario,
        contrato=contrato,
        ativo=True,
        papel=Usuario.Perfil.ADMIN,
    ).exists()


def carregar_minha_mesa(usuario, contrato_id=None, *, hoje=None, limite=10, incluir_ignorados=False):
    contratos = list(contratos_acessiveis(usuario))
    contrato = resolver_contrato(usuario, contrato_id)
    if contrato is None:
        return {"contratos": contratos, "contrato": None, "janelas": [], "perfil_erro": ""}

    hoje = hoje or timezone.localdate()
    perfil_modelo = PerfilContrato.perfil_vigente(contrato, hoje)
    perfil = None
    perfil_erro = ""
    if perfil_modelo is not None:
        try:
            perfil = perfil_de_dict(perfil_modelo.definicao)
        except ErroPerfil as erro:
            perfil_erro = f"O perfil vigente não pode alimentar as janelas: {erro}"
    else:
        perfil_erro = "Este contrato ainda não tem um perfil vigente."

    docs = _documentos_com_historico(contrato)
    erros = _erros_abertos(contrato, perfil, docs, incluir_ignorados=incluir_ignorados) if perfil else []
    if perfil and perfil.comparar_id_cliente:
        erros.extend(
            _pendencias_ids(
                contrato,
                perfil,
                incluir_ignorados=incluir_ignorados,
            )
        )
        erros.sort(
            key=lambda item: (
                item["data_desde"] or date.min,
                item["codigo"].casefold(),
            )
        )
    prazos_analise, prazos_devolucao = _janelas_prazo(perfil, docs, hoje) if perfil else ([], [])
    cronograma = _itens_cronograma(contrato, hoje)
    recusadas = _linhas_recusadas(contrato)

    janelas = []
    if perfil:
        janela_erros = _janela("erros", "Erros a corrigir", erros, limite)
        if perfil.comparar_id_cliente:
            nome_id_cliente = perfil.nome_id_cliente or "ID do cliente"
            janela_erros["contagens_pendencias_id"] = [
                {
                    "rotulo": f"Falta no {nome_id_cliente}",
                    "quantidade": sum(
                        item["tipo_pendencia"] == PENDENCIA_FALTA_NO_PW
                        for item in erros
                    ),
                },
                {
                    "rotulo": "Falta no nosso ID",
                    "quantidade": sum(
                        item["tipo_pendencia"] == PENDENCIA_FALTA_NO_NOSSO_ID
                        for item in erros
                    ),
                },
            ]
        janelas.append(janela_erros)
        if perfil.prazos is not None:
            regras_analise = [regra for regra in perfil.prazos.regras if regra.inicio == "emissao" and regra.fim == "analise"]
            regras_devolucao = [regra for regra in perfil.prazos.regras if regra.inicio == "analise" and regra.fim == "proxima_emissao"]
            if regras_analise:
                janelas.append(_janela(PRAZO_ANALISE, _rotulo_regras_regras(regras_analise), prazos_analise, limite))
            if regras_devolucao:
                janelas.append(_janela(PRAZO_DEVOLUCAO, _rotulo_regras_regras(regras_devolucao), prazos_devolucao, limite))
        if _pode_editar_perfil(usuario, contrato):
            janelas.append(_janela_classes_sem_escopo(contrato, perfil))
    janelas.extend(
        (
            _janela("cronograma", TIPOS_JANELA["cronograma"], cronograma, limite),
            _janela("recusadas", TIPOS_JANELA["recusadas"], recusadas, limite),
        )
    )
    indices_titulo_id = _indices_vigentes_do_contrato(contrato)
    janela_titulo_id = _janela(
        JANELA_TITULO_DIFERENTE_ID,
        TIPOS_JANELA[JANELA_TITULO_DIFERENTE_ID],
        _pendencias_titulo_id(
            contrato,
            usuario,
            incluir_ignorados=incluir_ignorados,
            indices=indices_titulo_id,
        ),
        limite,
    )
    indice_vigente = indices_titulo_id[0] if indices_titulo_id else None
    janela_titulo_id["id_vigente"] = (
        {
            "codigo": indice_vigente.codigo,
            "importado_em": timezone.localtime(indice_vigente.importado_em).date(),
        }
        if indice_vigente
        else None
    )
    janelas.append(janela_titulo_id)
    return {
        "contratos": contratos,
        "contrato": contrato,
        "perfil_erro": perfil_erro,
        "janelas": janelas,
        "perfil": perfil,
    }


def carregar_resumo_inicio(usuario, contrato_id=None, *, hoje=None):
    hoje = hoje or timezone.localdate()
    mesa = carregar_minha_mesa(usuario, contrato_id, hoje=hoje, limite=0)
    cards_janelas = []
    for janela in mesa["janelas"]:
        quantidade = (
            sum(item["quantidade"] for item in janela["todos"])
            if janela["id"] == "recusadas"
            else janela["quantidade"]
        )
        if not quantidade:
            continue
        cards_janelas.append(
            {
                "id": janela["id"],
                "quantidade": quantidade,
                "texto": _TEXTOS_RESUMO[janela["id"]],
            }
        )

    resumo_atrasos = _resumo_atrasos(mesa)
    documentos_analise = _itens_resumo_analise_cliente(mesa)
    urls = _urls_inicio(mesa.get("contrato"), mesa.get("perfil"))
    janela_analise = next(
        (janela for janela in mesa["janelas"] if janela["id"] == PRAZO_ANALISE),
        None,
    )
    perfil = mesa.get("perfil")
    mostrar_alerta_vencimento = bool(perfil and perfil.prazos is not None and janela_analise)
    dias_alerta_vencimento = (
        perfil.prazos.dias_alerta_vencimento if mostrar_alerta_vencimento else None
    )
    documentos_vencendo = {
        item["documento"].pk
        for item in janela_analise["todos"]
        if not item["atrasado"] and item["dias"] <= dias_alerta_vencimento
    } if mostrar_alerta_vencimento else set()
    janela_titulo_id = next(
        (janela for janela in mesa["janelas"] if janela["id"] == JANELA_TITULO_DIFERENTE_ID),
        None,
    )
    mostrar_atividade = _pode_ver_atividade(usuario, mesa.get("contrato")) if mesa.get("contrato") else False
    from tarefas.servicos import carregar_resumo_tarefas

    resumo_tarefas = (
        carregar_resumo_tarefas(usuario, mesa["contrato"], hoje=hoje)
        if mesa.get("contrato")
        else {
            "tarefas_minhas": [],
            "tarefas_minhas_total": 0,
            "tarefas_equipe_resumo": None,
            "tarefas_url": reverse("tarefas:lista"),
        }
    )
    return {
        **mesa,
        **resumo_tarefas,
        "cards_janelas": cards_janelas,
        "cards_pacotes": _cards_pacotes_analise(mesa),
        "resumo_atrasos": resumo_atrasos,
        "indicadores_inicio": _indicadores_inicio(
            usuario, mesa, cards_janelas, resumo_atrasos, hoje, urls
        ),
        "pacotes_pendencias": _pacotes_pendencias(mesa),
        "faixas_atraso_inicio": _faixas_atraso_inicio(mesa, resumo_atrasos),
        "documentos_analise_cliente": documentos_analise[:5],
        "mostrar_alerta_vencimento": mostrar_alerta_vencimento,
        "dias_alerta_vencimento": dias_alerta_vencimento,
        "quantidade_documentos_vencendo": len(documentos_vencendo),
        "quantidade_titulos_id": janela_titulo_id["quantidade"] if janela_titulo_id else 0,
        "pacotes_destaque": _pacotes_destaque(mesa, documentos_analise),
        "atividade_recente": _atividade_recente(
            usuario, mesa.get("contrato"), permitido=mostrar_atividade
        ),
        "mostrar_atividade": mostrar_atividade,
        "pode_importar_pw": bool(usuario.is_staff),
        "urls_inicio": urls,
        "alerta_backup": alerta_backup_para_usuario(usuario),
    }


def carregar_abertas(usuario, contrato_id=None, *, hoje=None):
    mesa = carregar_minha_mesa(usuario, contrato_id, hoje=hoje, limite=None)
    janelas = {janela["id"]: janela for janela in mesa["janelas"]}
    cartoes = []
    contrato = mesa.get("contrato")
    for identificador, texto, quantidade in _resumo_janelas(mesa):
        janela = janelas[identificador]
        cartoes.append(
            {
                "id": identificador,
                "titulo": janela["titulo"],
                "quantidade": quantidade,
                "ajuda": texto,
                "url": (
                    f"{reverse('acoes:janela', args=(identificador,))}?"
                    f"{urlencode({'contrato': contrato.pk})}"
                    if contrato is not None else "#"
                ),
            }
        )
    return {**mesa, "cartoes_abertas": cartoes}


def _resumo_janelas(mesa):
    for janela in mesa["janelas"]:
        quantidade = (
            sum(item["quantidade"] for item in janela["todos"])
            if janela["id"] == "recusadas"
            else janela["quantidade"]
        )
        if quantidade:
            yield janela["id"], _TEXTOS_RESUMO[janela["id"]], quantidade


def _urls_inicio(contrato, perfil=None):
    if contrato is None:
        return {}
    query = urlencode({"contrato": contrato.pk})
    grupo_aprovado = next(
        (
            grupo
            for grupo in (perfil.painel.grupos if perfil else ())
            if grupo.id.casefold() == "aprovado"
        ),
        None,
    )
    query_aprovados = urlencode(
        {"contrato": contrato.pk, "situacao": grupo_aprovado.id}
    ) if grupo_aprovado else query
    return {
        "pendencias": f"{reverse('acoes:pendencias')}?{query}",
        "pendencias_prazo_analise": (
            f"{reverse('acoes:pendencias')}?{query}#janela-{PRAZO_ANALISE}"
        ),
        "pendencias_titulo_id": (
            f"{reverse('acoes:pendencias')}?{query}#janela-{JANELA_TITULO_DIFERENTE_ID}"
        ),
        "abertas": f"{reverse('acoes:abertas')}?{query}",
        "analise_cliente": f"{reverse('acoes:janela', args=(PRAZO_ANALISE,))}?{query}",
        "atrasados": f"{reverse('acoes:atrasados')}?{query}",
        "documentos": f"{reverse('documentos_lista')}?{query}",
        "documentos_aprovados": f"{reverse('documentos_lista')}?{query_aprovados}",
        "importar_pw": f"{reverse('importar_situacao_pw')}?{query}",
        "atividade": f"{reverse('atividade')}?{query}",
    }


def _indicadores_inicio(usuario, mesa, cards_janelas, resumo_atrasos, hoje, urls):
    contrato = mesa.get("contrato")
    perfil = mesa.get("perfil")
    janela_analise = next(
        (janela for janela in mesa["janelas"] if janela["id"] == PRAZO_ANALISE),
        None,
    )
    documentos_analise = {
        item["documento"].pk for item in janela_analise["todos"]
    } if janela_analise else set()
    grupo_aprovado = next(
        (
            grupo
            for grupo in (perfil.painel.grupos if perfil else ())
            if grupo.id.casefold() == "aprovado"
        ),
        None,
    )
    aprovados_na_semana = 0
    if contrato is not None and perfil is not None and grupo_aprovado is not None:
        situacoes = Analise.objects.filter(
            emissao__documento__contrato=contrato,
            data_analise__gte=hoje - timedelta(days=6),
            data_analise__lte=hoje,
        ).values_list("situacao", flat=True)
        aprovados_na_semana = sum(
            1 for situacao in situacoes
            if classificar(perfil, situacao).id == grupo_aprovado.id
        )

    atrasos_por_lado = _itens_atrasados_por_lado(mesa)

    return [
        {
            "id": "pendencias",
            "titulo": "Pendências abertas",
            "quantidade": sum(card["quantidade"] for card in cards_janelas),
            "descricao": "Itens com ação pendente",
            "ajuda": "Pendências abertas em todas as janelas",
            "url": urls.get("abertas", "#"),
        },
        {
            "id": "analise-cliente",
            "titulo": "Em análise do cliente",
            "quantidade": len(documentos_analise),
            "descricao": "Aguardando retorno do cliente",
            "ajuda": "Documentos aguardando análise do cliente",
            "url": urls.get("analise_cliente", "#"),
        },
        {
            "id": "atrasados",
            "titulo": "Atrasados",
            "quantidade": resumo_atrasos["quantidade"],
            "descricao": (
                f"{_rotulo_quantidade(len(atrasos_por_lado[PRAZO_ANALISE]), 'análise atrasada', 'análises atrasadas')} · "
                f"{_rotulo_quantidade(len(atrasos_por_lado[PRAZO_DEVOLUCAO]), 'revisão atrasada', 'revisões atrasadas')}"
            ),
            "ajuda": "Análise atrasada é do cliente; revisões atrasadas são da contratada",
            "url": urls.get("atrasados", "#"),
        },
        {
            "id": "aprovados",
            "titulo": "Aprovados na semana",
            "quantidade": aprovados_na_semana,
            "descricao": "Análises aprovadas nos últimos 7 dias",
            "ajuda": "Documentos com análise aprovada nos últimos 7 dias",
            "url": urls.get("documentos_aprovados", urls.get("documentos", "#")),
        },
    ]


def _itens_resumo_analise_cliente(mesa):
    janela = next(
        (janela for janela in mesa["janelas"] if janela["id"] == PRAZO_ANALISE),
        None,
    )
    if janela is None:
        return []

    itens_por_documento = {}
    for item in janela["todos"]:
        documento = item["documento"]
        itens_por_documento.setdefault(documento.pk, item)

    itens = sorted(
        itens_por_documento.values(),
        key=lambda item: (
            0 if item["atrasado"] else 1,
            -item["dias"] if item["atrasado"] else item["dias"],
            item["codigo"].casefold(),
        ),
    )
    contrato = mesa.get("contrato")
    return [
        {
            "documento": item["documento"],
            "codigo": item["codigo"],
            "titulo": item["titulo"],
            "atrasado": item["atrasado"],
            "dias": item["dias"],
            "etiqueta": (
                f"Atrasado há {item['dias']} {'dia' if item['dias'] == 1 else 'dias'}"
                if item["atrasado"]
                else "Em análise"
            ),
            "url": reverse(
                "documento_pasta", args=(contrato.pk, item["documento"].pk)
            ) if contrato is not None else "#",
        }
        for item in itens
    ]


def _pacote_do_documento(perfil, documento):
    pacote_perfil = perfil.painel.pacote
    if pacote_perfil is None and not perfil.painel.categorias:
        return None
    codigo = interpretar(perfil, documento.identificador_base)
    if isinstance(codigo, ErroCodigo):
        return None
    if pacote_perfil is not None:
        valores = tuple(codigo.segmentos.get(nome, "") for nome in pacote_perfil.segmentos)
        if not all(valores):
            return None
        codigo_pacote = "".join(valores)
        nome = codigo.significados.get(pacote_perfil.nome_de) if pacote_perfil.nome_de else None
        rotulo = f"{codigo_pacote} · {nome}" if nome else codigo_pacote
        return valores, rotulo
    categoria = classificar_categoria(perfil, codigo.segmentos)
    return (categoria.id, categoria.rotulo) if categoria else None


def _pacotes_pendencias(mesa):
    perfil = mesa.get("perfil")
    if perfil is None:
        return []

    documentos = {}
    for janela in mesa["janelas"]:
        if janela["id"] == "recusadas":
            continue
        for item in janela["todos"]:
            documento = item.get("documento")
            if documento is not None:
                documentos.setdefault(documento.pk, documento)
    if not documentos:
        return []

    mapa_atrasos = _mapa_documentos_atrasados(mesa)
    faixas = _faixas_atraso_perfil(perfil)
    faixa_critica = faixas[-1].rotulo.casefold() if faixas else None
    por_pacote = {}
    for documento in documentos.values():
        pacote = _pacote_do_documento(perfil, documento)
        if pacote is None:
            continue
        identificador, rotulo = pacote
        grupo = por_pacote.setdefault(
            identificador,
            {"rotulo": rotulo, "documentos": set(), "critico": False, "atraso": False},
        )
        grupo["documentos"].add(documento.pk)
        atraso = mapa_atrasos.get(documento.pk)
        if atraso is not None:
            grupo["atraso"] = True
            if faixa_critica and (atraso.get("faixa_atraso") or "").casefold() == faixa_critica:
                grupo["critico"] = True

    resultado = [
        {
            "rotulo": grupo["rotulo"],
            "quantidade": len(grupo["documentos"]),
            "situacao": "Crítico" if grupo["critico"] else "Atenção" if grupo["atraso"] else "Em dia",
            "tom": "critico" if grupo["critico"] else "atencao" if grupo["atraso"] else "em-dia",
        }
        for grupo in por_pacote.values()
    ]
    maior_quantidade = max((item["quantidade"] for item in resultado), default=0)
    for item in resultado:
        item["percentual"] = round(item["quantidade"] * 100 / maior_quantidade) if maior_quantidade else 0
    return sorted(resultado, key=lambda item: (-item["quantidade"], item["rotulo"].casefold()))


def _faixas_atraso_inicio(mesa, resumo_atrasos):
    por_rotulo = {item["rotulo"]: item["quantidade"] for item in resumo_atrasos["faixas"]}
    return [
        {
            "rotulo": faixa.rotulo,
            "quantidade": por_rotulo.get(faixa.rotulo, 0),
            "tom": min(indice + 1, 4),
        }
        for indice, faixa in enumerate(_faixas_atraso_perfil(mesa.get("perfil")))
    ]


def _pacotes_destaque(mesa, documentos_analise):
    perfil = mesa.get("perfil")
    if perfil is None:
        return []
    por_pacote = {}
    for item in documentos_analise:
        documento_id = item["documento"].pk
        pacote = _pacote_do_documento(perfil, item["documento"])
        if pacote is None:
            continue
        identificador, rotulo = pacote
        grupo = por_pacote.setdefault(
            identificador, {"rotulo": rotulo, "documentos": set()}
        )
        grupo["documentos"].add(documento_id)
    pacotes = [
        {"rotulo": grupo["rotulo"], "quantidade": len(grupo["documentos"])}
        for grupo in por_pacote.values()
    ]
    return sorted(pacotes, key=lambda item: (-item["quantidade"], item["rotulo"].casefold()))[:3]


def _atividade_recente(usuario, contrato, *, permitido=False):
    if contrato is None or not permitido:
        return []
    from registro.servicos import carregar_eventos

    eventos = sorted(
        carregar_eventos(contrato),
        key=lambda evento: evento["data_hora"],
        reverse=True,
    )[:3]
    recentes = []
    for evento in eventos:
        query = urlencode({"contrato": contrato.pk, "evento": evento["chave"]})
        recentes.append(
            {
                "resumo": evento["resumo"],
                "data_hora": evento["data_hora"],
                "url": f"{reverse('atividade')}?{query}",
            }
        )
    return recentes


def _pode_ver_atividade(usuario, contrato):
    return bool(
        usuario.is_staff
        or usuario.is_superuser
        or Participacao.objects.filter(
            usuario=usuario,
            contrato=contrato,
            papel=Usuario.Perfil.ADMIN,
            ativo=True,
        ).exists()
    )


def _cards_pacotes_analise(mesa):
    perfil = mesa.get("perfil")
    if perfil is None:
        return []
    pacote_perfil = perfil.painel.pacote
    if pacote_perfil is None and not perfil.painel.categorias:
        return []
    janela = next(
        (item for item in mesa["janelas"] if item["id"] == PRAZO_ANALISE),
        None,
    )
    if janela is None:
        return []

    documentos_por_pacote = defaultdict(set)
    rotulos_por_pacote = {}
    for item in janela["todos"]:
        documento = item["documento"]
        codigo = interpretar(perfil, documento.identificador_base)
        if isinstance(codigo, ErroCodigo):
            continue
        if pacote_perfil is not None:
            valores = tuple(codigo.segmentos.get(nome, "") for nome in pacote_perfil.segmentos)
            if not all(valores):
                continue
            identificador = valores
            rotulo_codigo = "".join(valores)
            nome = codigo.significados.get(pacote_perfil.nome_de) if pacote_perfil.nome_de else None
            rotulo = f"{rotulo_codigo} · {nome}" if nome else rotulo_codigo
        else:
            categoria = classificar_categoria(perfil, codigo.segmentos)
            if categoria is None:
                continue
            identificador = categoria.id
            rotulo = categoria.rotulo
        documentos_por_pacote[identificador].add(documento.pk)
        rotulos_por_pacote[identificador] = rotulo

    pacotes = [
        {
            "id": "".join(identificador) if isinstance(identificador, tuple) else identificador,
            "rotulo": rotulos_por_pacote[identificador],
            "quantidade": len(documentos),
        }
        for identificador, documentos in documentos_por_pacote.items()
        if len(documentos) >= 2
    ]
    return sorted(
        pacotes,
        key=lambda pacote: (-pacote["quantidade"], pacote["rotulo"].casefold()),
    )[:6]


def _resumo_atrasos(mesa):
    documentos_atrasados = _mapa_documentos_atrasados(mesa)

    quantidades = defaultdict(int)
    tons = {}
    for item in documentos_atrasados.values():
        rotulo = item.get("faixa_atraso")
        if rotulo:
            quantidades[rotulo] += 1
            tons[rotulo] = max(tons.get(rotulo, 0), item["faixa_atraso_tom"])

    faixas = []
    for faixa in _faixas_atraso_perfil(mesa.get("perfil")):
        quantidade = quantidades.get(faixa.rotulo, 0)
        if quantidade:
            faixas.append(
                {
                    "rotulo": faixa.rotulo,
                    "quantidade": quantidade,
                    "tom": tons[faixa.rotulo],
                }
            )
    return {"quantidade": len(documentos_atrasados), "faixas": faixas}


def _mapa_documentos_atrasados(mesa):
    documentos_atrasados = {}
    for janela in mesa["janelas"]:
        if janela["id"] not in {PRAZO_ANALISE, PRAZO_DEVOLUCAO}:
            continue
        for item in janela["todos"]:
            if not item["atrasado"]:
                continue
            documento_id = item["documento"].pk
            atual = documentos_atrasados.get(documento_id)
            if atual is None or item["dias"] > atual["dias"]:
                documentos_atrasados[documento_id] = {**item, "janela_id": janela["id"]}
    return documentos_atrasados


def _itens_atrasados_por_lado(mesa):
    itens_por_lado = {PRAZO_ANALISE: [], PRAZO_DEVOLUCAO: []}
    for item in _mapa_documentos_atrasados(mesa).values():
        itens_por_lado[item["janela_id"]].append(item)
    for itens in itens_por_lado.values():
        itens.sort(key=lambda item: (-item["dias"], item["codigo"].casefold()))
    return itens_por_lado


def _rotulo_quantidade(quantidade, singular, plural):
    return f"{quantidade} {singular if quantidade == 1 else plural}"


def carregar_atrasados(usuario, contrato_id=None, *, hoje=None):
    mesa = carregar_minha_mesa(usuario, contrato_id, hoje=hoje, limite=None)
    itens_por_lado = _itens_atrasados_por_lado(mesa)
    return {
        **mesa,
        "atrasos_cliente": itens_por_lado[PRAZO_ANALISE],
        "atrasos_nossos": itens_por_lado[PRAZO_DEVOLUCAO],
        "quantidade_atrasados": sum(len(itens) for itens in itens_por_lado.values()),
    }


def carregar_atrasados_lado(usuario, contrato_id, lado, *, hoje=None):
    lados = {
        "analise": (PRAZO_ANALISE, "Análise atrasada", "atrasos_cliente"),
        "revisoes": (PRAZO_DEVOLUCAO, "Revisões atrasadas", "atrasos_nossos"),
    }
    if lado not in lados:
        raise ValueError("Lado de atraso desconhecido.")
    identificador, titulo, chave_itens = lados[lado]
    contexto = carregar_atrasados(usuario, contrato_id, hoje=hoje)
    return {
        **contexto,
        "lado": lado,
        "janela_id": identificador,
        "titulo_lado": titulo,
        "itens_atrasados": contexto[chave_itens],
    }


def _faixas_atraso_perfil(perfil):
    if perfil is None or perfil.prazos is None:
        return ()
    faixas = list(perfil.prazos.faixas_atraso or ())
    rotulos = {faixa.rotulo for faixa in faixas}
    for regra in perfil.prazos.regras:
        for faixa in regra.faixas_atraso or ():
            if faixa.rotulo not in rotulos:
                faixas.append(faixa)
                rotulos.add(faixa.rotulo)
    return tuple(faixas)


def carregar_janela(usuario, contrato_id, tipo, *, hoje=None):
    if tipo not in TIPOS_JANELA:
        raise ValueError("Janela desconhecida.")
    mesa = carregar_minha_mesa(usuario, contrato_id, hoje=hoje, limite=None)
    janela = next((item for item in mesa["janelas"] if item["id"] == tipo), None)
    if janela is None:
        janela = {"id": tipo, "titulo": TIPOS_JANELA[tipo], "quantidade": 0, "itens": []}
    return {**mesa, "janela": janela}


def carregar_ignorados(usuario, contrato_id, *, hoje=None):
    mesa = carregar_minha_mesa(usuario, contrato_id, hoje=hoje, limite=None, incluir_ignorados=True)
    janelas = [
        item for item in mesa["janelas"]
        if item["id"] in {"erros", JANELA_TITULO_DIFERENTE_ID}
    ]
    itens = [
        item for janela in janelas for item in janela["todos"]
        if item["ultima_acao"]
        and item["ultima_acao"].acao == AcaoPendencia.Acao.IGNORAR
        and item["ultima_acao"].resolvida_em is None
    ]
    return {
        **mesa,
        "janela": {"id": "ignorados", "titulo": "Pendências ignoradas", "quantidade": len(itens), "itens": itens, "todos": itens},
    }


def registrar_acao(usuario, contrato_id, documento_id, tipo_pendencia, acao, motivo=""):
    contrato = resolver_contrato(usuario, contrato_id)
    if contrato is None:
        raise PermissionDenied("Você não participa deste contrato.")
    if acao not in AcaoPendencia.Acao.values:
        raise ValueError("Ação desconhecida.")
    motivo = (motivo or "").strip()
    if acao == AcaoPendencia.Acao.IGNORAR and not motivo:
        raise ValueError("Informe o motivo para ignorar a pendência.")

    dados = carregar_minha_mesa(usuario, contrato.pk, limite=None)
    pendencia = next(
        (
            item for janela in dados["janelas"] for item in janela["todos"]
            if item["documento"].pk == int(documento_id)
            and item["tipo_pendencia"] == tipo_pendencia
        ),
        None,
    )
    if pendencia is None:
        raise ValueError("A pendência já não está aberta para ação.")

    texto_email = ""
    if (
        acao == AcaoPendencia.Acao.PEDIR_CORRECAO
        and tipo_pendencia not in _PENDENCIAS_ID
    ):
        texto_email = _texto_email_correcao(pendencia)
    registro = AcaoPendencia(
        contrato=contrato,
        documento=pendencia["documento"],
        tipo_pendencia=tipo_pendencia,
        acao=acao,
        motivo=motivo,
        texto_email=texto_email,
        situacao_referencia=pendencia["situacao"],
        revisao_referencia=pendencia["revisao"],
        data_referencia=pendencia["data_situacao"],
        usuario=usuario,
    )
    registro.full_clean(exclude=("criado_em", "resolvida_em"))
    registro.save()
    return registro


def reativar_ignorado(usuario, contrato_id, documento_id, tipo_pendencia):
    contrato = resolver_contrato(usuario, contrato_id)
    if contrato is None:
        raise PermissionDenied("Você não participa deste contrato.")
    dados = carregar_ignorados(usuario, contrato.pk)
    ignorado = next(
        (
            item for item in dados["janela"]["todos"]
            if item["documento"].pk == int(documento_id)
            and item["tipo_pendencia"] == tipo_pendencia
        ),
        None,
    )
    if ignorado is None:
        raise ValueError("A pendência ignorada já não está disponível para reativação.")
    acao = ignorado["ultima_acao"]
    acao.resolvida_em = timezone.now()
    acao._history_user = usuario
    acao.save(update_fields=("resolvida_em",))
    return acao


def _documentos_com_historico(contrato):
    analises = Analise.objects.order_by(
        F("data_analise").desc(nulls_last=True), "-registrado_em", "-pk"
    )
    emissoes = Emissao.objects.order_by("data_emissao", "pk").prefetch_related(
        Prefetch("analises", queryset=analises)
    )
    return list(
        Documento.objects.filter(contrato=contrato, emissoes__isnull=False)
        .distinct()
        .prefetch_related(Prefetch("emissoes", queryset=emissoes))
        .order_by("identificador_base", "pk")
    )


def _erros_abertos(contrato, perfil, documentos, *, incluir_ignorados=False):
    grupos_ocultos = {
        grupo.id: grupo for grupo in perfil.painel.grupos if grupo.oculto_no_painel
    }
    if not grupos_ocultos:
        return []
    ultimas_acoes = _ultimas_acoes_pendencias(contrato)

    itens = []
    for documento in documentos:
        emissao, analise = _situacao_e_analise_atual(documento)
        if emissao is None or analise is None:
            continue
        grupo = classificar(perfil, analise.situacao)
        if not grupo.oculto_no_painel or grupo.id not in grupos_ocultos:
            continue
        ultima_acao = ultimas_acoes.get((documento.pk, grupo.id))
        if (
            ultima_acao
            and ultima_acao.acao == AcaoPendencia.Acao.IGNORAR
            and ultima_acao.resolvida_em is None
            and not incluir_ignorados
        ):
            continue
        if (
            ultima_acao
            and ultima_acao.acao == AcaoPendencia.Acao.JA_CORRIGI
            and ultima_acao.situacao_referencia != analise.situacao
        ):
            ultima_acao = None
        data_situacao = analise.data_analise
        if data_situacao is None and analise.registrado_em:
            data_situacao = timezone.localtime(analise.registrado_em).date()
        if data_situacao is None:
            data_situacao = emissao.data_emissao
        itens.append(
            {
                "documento": documento,
                "codigo": documento.identificador_base,
                "titulo": documento.titulo or "(sem título)",
                "situacao": analise.situacao,
                "grupo": grupo.rotulo,
                "tipo_pendencia": grupo.id,
                "data_situacao": data_situacao,
                "data_desde": analise.data_analise or data_situacao,
                "emissao": emissao,
                "revisao": emissao.revisao,
                "versao": emissao.versao,
                "quem_lancou": _nome_usuario(analise.registrado_por),
                "ultima_acao": ultima_acao,
                "ultima_acao_por": _nome_usuario(ultima_acao.usuario) if ultima_acao else "",
            }
        )
    return sorted(itens, key=lambda item: (item["data_desde"], item["codigo"].casefold()))


def _indices_vigentes_do_contrato(contrato):
    return list(
        IndiceDocumentos.objects.filter(
            contrato=contrato,
            vigente=True,
            substituido_por__isnull=True,
        ).order_by("-importado_em", "-pk")
    )


def _pendencias_ids(contrato, perfil, *, incluir_ignorados=False):
    indices = _indices_vigentes_do_contrato(contrato)
    ids_nosso_id = {
        indice.pk
        for indice in indices
        if indice.fonte == IndiceDocumentos.Fonte.EXCEL_ID
    }
    if not ids_nosso_id:
        ids_nosso_id = {indice.pk for indice in indices}
    indices_por_id = {indice.pk: indice for indice in indices}
    ids_consultados = ids_nosso_id | {
        indice.pk
        for indice in indices
        if indice.fonte == IndiceDocumentos.Fonte.EXTRACAO_PW
    }
    itens = ItemPrevisto.objects.filter(
        indice_id__in=ids_consultados,
        excluido=False,
    ).select_related("indice", "documento")

    documentos_nosso_id = {}
    documentos_id_cliente = {}
    for item in itens:
        indice = indices_por_id[item.indice_id]
        if (
            item.indice_id in ids_nosso_id
            and indice.conta_no_previsto
        ):
            documentos_nosso_id.setdefault(item.documento_id, item.documento)
        if indice.fonte == IndiceDocumentos.Fonte.EXTRACAO_PW:
            documentos_id_cliente.setdefault(item.documento_id, item.documento)

    ultimas_acoes = _ultimas_acoes_pendencias(contrato)
    nome_id_cliente = perfil.nome_id_cliente or "ID do cliente"
    grupos = (
        (
            PENDENCIA_FALTA_NO_PW,
            f"Falta no {nome_id_cliente}",
            "Ausente no ID do cliente",
            f"Pedir inclusão no {nome_id_cliente}",
            documentos_nosso_id.keys() - documentos_id_cliente.keys(),
        ),
        (
            PENDENCIA_FALTA_NO_NOSSO_ID,
            "Falta no nosso ID",
            "Ausente no nosso ID",
            "",
            documentos_id_cliente.keys() - documentos_nosso_id.keys(),
        ),
    )
    itens_pendencia = []
    for tipo, rotulo, situacao, rotulo_acao, ids_documentos in grupos:
        for documento_id in ids_documentos:
            documento = (
                documentos_nosso_id.get(documento_id)
                or documentos_id_cliente.get(documento_id)
            )
            if documento.cancelado_em:
                continue
            ultima_acao = ultimas_acoes.get((documento.pk, tipo))
            if (
                ultima_acao
                and ultima_acao.acao == AcaoPendencia.Acao.IGNORAR
                and ultima_acao.resolvida_em is None
                and not incluir_ignorados
            ):
                continue
            itens_pendencia.append(
                {
                    "documento": documento,
                    "codigo": documento.identificador_base,
                    "titulo": documento.titulo or "(sem título)",
                    "situacao": situacao,
                    "grupo": rotulo,
                    "tipo_pendencia": tipo,
                    "data_situacao": None,
                    "data_desde": None,
                    "emissao": None,
                    "revisao": "—",
                    "versao": None,
                    "quem_lancou": "Sistema",
                    "ultima_acao": ultima_acao,
                    "ultima_acao_por": _nome_usuario(ultima_acao.usuario) if ultima_acao else "",
                    "rotulo_acao": rotulo_acao,
                }
            )
    return itens_pendencia


def _pendencias_titulo_id(contrato, usuario, *, incluir_ignorados=False, indices=None):
    if indices is None:
        indices = _indices_vigentes_do_contrato(contrato)
    itens_id = (
        ItemPrevisto.objects.filter(
            indice_id__in=[indice.pk for indice in indices],
            indice__vigente=True,
            indice__substituido_por__isnull=True,
            documento__contrato=contrato,
            excluido=False,
        )
        .select_related("indice", "documento")
        .order_by("-indice__importado_em", "-indice_id", "-pk")
    )
    por_documento = {}
    for item in itens_id:
        titulo_id = (item.titulo or "").strip()
        if titulo_id and item.documento_id not in por_documento:
            por_documento[item.documento_id] = (item, titulo_id)

    ultimas_acoes = _ultimas_acoes_pendencias(contrato)
    pode_editar_titulo = _pode_editar_perfil(usuario, contrato)
    pendencias = []
    for documento_id, (item, titulo_id) in por_documento.items():
        documento = item.documento
        titulo_atual = documento.titulo or ""
        if titulo_atual.strip().casefold() == titulo_id.casefold():
            continue
        ultima_acao = ultimas_acoes.get(
            (documento.pk, PENDENCIA_TITULO_DIFERENTE_ID)
        )
        if (
            ultima_acao
            and ultima_acao.acao == AcaoPendencia.Acao.IGNORAR
            and ultima_acao.resolvida_em is None
            and not incluir_ignorados
        ):
            continue
        pendencias.append(
            {
                "documento": documento,
                "codigo": documento.identificador_base,
                "titulo": titulo_atual or "(sem título)",
                "titulo_atual": titulo_atual,
                "titulo_id": titulo_id,
                "codigo_id": item.indice.codigo,
                "nome_id": item.indice.arquivo_nome,
                "situacao": "Título diferente do ID",
                "grupo": "Título diferente do ID",
                "tipo_pendencia": PENDENCIA_TITULO_DIFERENTE_ID,
                "data_situacao": None,
                "data_desde": None,
                "emissao": None,
                "revisao": "—",
                "versao": None,
                "quem_lancou": "Sistema",
                "ultima_acao": ultima_acao,
                "ultima_acao_por": _nome_usuario(ultima_acao.usuario) if ultima_acao else "",
                "pode_editar_titulo": pode_editar_titulo,
            }
        )
    return sorted(pendencias, key=lambda item: item["codigo"].casefold())


def _ultimas_acoes_pendencias(contrato):
    acoes = AcaoPendencia.objects.filter(contrato=contrato).select_related("usuario").order_by(
        "-criado_em", "-pk"
    )
    ultimas_acoes = {}
    for acao in acoes:
        ultimas_acoes.setdefault((acao.documento_id, acao.tipo_pendencia), acao)
    return ultimas_acoes


def _situacao_e_analise_atual(documento):
    emissao = max(
        documento.emissoes.all(),
        key=lambda item: (item.data_emissao, item.pk),
        default=None,
    )
    if emissao is None:
        return None, None
    analise = next(iter(emissao.analises.all()), None)
    return emissao, analise


def _janelas_prazo(perfil, documentos, hoje):
    if perfil.prazos is None:
        return [], []
    regras_analise = [
        regra for regra in perfil.prazos.regras
        if regra.inicio == "emissao" and regra.fim == "analise"
    ]
    regras_devolucao = [
        regra for regra in perfil.prazos.regras
        if regra.inicio == "analise" and regra.fim == "proxima_emissao"
    ]
    return (
        _itens_regras_prazo(perfil, regras_analise, documentos, hoje),
        _itens_regras_prazo(perfil, regras_devolucao, documentos, hoje),
    )


def _itens_regras_prazo(perfil, regras, documentos, hoje):
    itens = []
    feriados = feriados_prazo(perfil.prazos, documentos, hoje)
    for regra in regras:
        for documento in documentos:
            for item_prazo in emissoes_abertas_prazo(perfil, regra, documento, hoje, feriados):
                avaliacao = item_prazo.avaliacao
                if avaliacao.situacao == "aberto_atrasado":
                    dias = avaliacao.dias_atraso
                    texto_prazo = f"Atrasado há {dias} {('dia' if dias == 1 else 'dias')}"
                    atrasado = True
                    faixas = (
                        regra.faixas_atraso
                        if regra.faixas_atraso is not None
                        else perfil.prazos.faixas_atraso
                    )
                    faixa_atraso, faixa_atraso_tom = _classificar_faixa_atraso(faixas, dias)
                else:
                    dias = dias_ate_vencimento(regra, hoje, avaliacao.vencimento, feriados)
                    if dias > perfil.prazos.dias_alerta_vencimento:
                        continue
                    texto_prazo = "Vence hoje" if dias == 0 else f"Vence em {dias} {('dia' if dias == 1 else 'dias')}"
                    atrasado = False
                    faixa_atraso = None
                    faixa_atraso_tom = None
                itens.append(
                    {
                        "documento": documento,
                        "codigo": documento.identificador_base,
                        "titulo": documento.titulo or "(sem título)",
                        "regra": regra,
                        "regra_rotulo": regra.rotulo,
                        "emissao": item_prazo.emissao,
                        "revisao": item_prazo.emissao.revisao,
                        "versao": item_prazo.emissao.versao,
                        "situacao": item_prazo.analise.situacao if item_prazo.analise else "Em análise",
                        "data_inicio": item_prazo.inicio,
                        "vencimento": avaliacao.vencimento,
                        "atrasado": atrasado,
                        "faixa_atraso": faixa_atraso,
                        "faixa_atraso_tom": faixa_atraso_tom,
                        "dias": dias,
                        "texto_prazo": texto_prazo,
                    }
                )
    return sorted(
        itens,
        key=lambda item: (
            0 if item["atrasado"] else 1,
            -item["dias"] if item["atrasado"] else item["dias"],
            item["codigo"].casefold(),
            item["revisao"],
        ),
    )


def _classificar_faixa_atraso(faixas, dias):
    if not faixas:
        return None, None
    for indice, faixa in enumerate(faixas):
        if faixa.ate_dias is None or dias <= faixa.ate_dias:
            return faixa.rotulo, min(indice + 1, 4)
    return faixas[-1].rotulo, min(len(faixas), 4)


def _itens_cronograma(contrato, hoje):
    itens = []
    limite = hoje + timedelta(days=_DIAS_CRONOGRAMA)
    for resultado in comparar_previsoes_cronograma(contrato, hoje=hoje):
        previsao = resultado.previsao
        vencido = resultado.status == "vencido_sem_emissao"
        futuro = resultado.status == "futuro" and previsao.data_prevista <= limite
        if not (vencido or futuro):
            continue
        dias = (hoje - previsao.data_prevista).days if vencido else (previsao.data_prevista - hoje).days
        texto_prazo = (
            f"Atrasado há {dias} {('dia' if dias == 1 else 'dias')}"
            if vencido
            else "Previsto para hoje" if dias == 0
            else f"Previsto em {dias} {('dia' if dias == 1 else 'dias')}"
        )
        itens.append(
            {
                "documento": previsao.documento,
                "codigo": previsao.documento.identificador_base,
                "titulo": previsao.documento.titulo or "(sem título)",
                "data_prevista": previsao.data_prevista,
                "vencido": vencido,
                "dias": dias,
                "texto_prazo": texto_prazo,
            }
        )
    return sorted(
        itens,
        key=lambda item: (0 if item["vencido"] else 1, -item["dias"] if item["vencido"] else item["dias"], item["codigo"].casefold()),
    )


def _linhas_recusadas(contrato):
    por_id = dict(
        InconsistenciaImportacao.objects.filter(
            importacao_id__contrato=contrato,
            resolvida_em__isnull=True,
        ).values("importacao_id").annotate(total=Count("pk")).values_list("importacao_id", "total")
    )
    por_situacao = dict(
        InconsistenciaImportacao.objects.filter(
            importacao_situacao__contrato=contrato,
            resolvida_em__isnull=True,
        ).values("importacao_situacao").annotate(total=Count("pk")).values_list("importacao_situacao", "total")
    )
    itens = []
    for importacao in ImportacaoID.objects.filter(pk__in=por_id).select_related("indice", "importado_por"):
        itens.append(
            {
                "importacao_id": importacao.pk,
                "arquivo": importacao.arquivo_nome,
                "tipo": "ID",
                "data_importacao": timezone.localtime(importacao.importado_em).date(),
                "quantidade": por_id[importacao.pk],
                "link_recusadas": True,
            }
        )
    for importacao in ImportacaoSituacao.objects.filter(pk__in=por_situacao).select_related("importado_por"):
        itens.append(
            {
                "importacao_id": importacao.pk,
                "arquivo": importacao.arquivo_nome,
                "tipo": "Situação PW",
                "data_importacao": timezone.localtime(importacao.importado_em).date(),
                "quantidade": por_situacao[importacao.pk],
                "link_recusadas": True,
            }
        )
    return sorted(itens, key=lambda item: (item["data_importacao"], item["tipo"], item["arquivo"].casefold()))


def _janela(identificador, rotulo, itens, limite):
    todos = list(itens)
    return {
        "id": identificador,
        "titulo": rotulo,
        "quantidade": len(todos),
        "itens": todos if limite is None else todos[:limite],
        "todos": todos,
    }


def _janela_classes_sem_escopo(contrato, perfil):
    grupos = {}
    documentos = Documento.objects.filter(contrato=contrato).order_by("identificador_base")
    for documento in documentos:
        atributos = documento.atributos if isinstance(documento.atributos, dict) else {}
        classe = str(atributos.get("classe") or documento.disciplina or "").strip()
        if not classe:
            continue
        tipo = str(atributos.get("tipo") or documento.tipo or "").strip()
        if escopo_do_documento(perfil, classe, tipo) is not None:
            continue
        grupo = grupos.setdefault(classe.casefold(), {"classe": classe, "documentos": []})
        grupo["documentos"].append(documento)

    itens = [
        {
            "classe": grupo["classe"],
            "quantidade": len(grupo["documentos"]),
            "documentos": grupo["documentos"],
        }
        for grupo in sorted(grupos.values(), key=lambda item: item["classe"].casefold())
    ]
    quantidade = sum(item["quantidade"] for item in itens)
    return {
        "id": CLASSES_SEM_ESCOPO,
        "titulo": TIPOS_JANELA[CLASSES_SEM_ESCOPO],
        "quantidade": quantidade,
        "itens": itens,
        "todos": itens,
    }


def _rotulo_regras_regras(regras):
    rotulos = []
    for regra in regras:
        if regra.rotulo not in rotulos:
            rotulos.append(regra.rotulo)
    return " / ".join(rotulos)


def _texto_email_correcao(pendencia):
    data = pendencia["data_situacao"].strftime("%d/%m/%Y") if pendencia["data_situacao"] else "sem data informada"
    revisao = f"{pendencia['revisao']}" + (
        f" versão {pendencia['versao']}" if pendencia["versao"] is not None else ""
    )
    return (
        "Prezados,\n\n"
        f"Solicitamos, por gentileza, a correção do registro do documento {pendencia['codigo']}, "
        f"revisão {revisao}, atualmente com a situação “{pendencia['situacao']}” desde {data}.\n\n"
        "Agradecemos a verificação e a atualização da situação no sistema.\n\n"
        "Atenciosamente,"
    )


def _nome_usuario(usuario):
    return usuario.get_full_name() or usuario.get_username() if usuario else "Sistema"
