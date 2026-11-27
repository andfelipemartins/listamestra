import json
from datetime import date, datetime

from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db.models import Q

from core.perfil import ErroPerfil, perfil_de_dict
from core.perfil.painel import classificar
from contratos.models import PerfilContrato
from documentos.models import Analise, CodigoDocumento, Documento, Emissao
from importacoes.models import (
    ImportacaoCronograma,
    ImportacaoID,
    ImportacaoSituacao,
    IndiceDocumentos,
    InconsistenciaImportacao,
    ItemPrevisto,
    PrevisaoEmissao,
    ReprocessamentoImportacao,
)
from painel.models import FotoPainel


ACOES = (
    ("criou", "Criou"),
    ("alterou", "Alterou"),
    ("excluiu", "Excluiu"),
    ("cancelou", "Cancelou"),
    ("reativou", "Reativou"),
    ("importou", "Importou"),
    ("reprocessou", "Reprocessou"),
)
_PREFIXO_SITUACAO_PADRAO = "[Planilha padrão] "


def carregar_eventos(contrato):
    """Monta uma linha por registro histórico e uma por lote de importação."""
    eventos = []
    documentos_existentes = dict(
        Documento.objects.filter(contrato=contrato).values_list("identificador_base", "pk")
    )
    documentos_existentes_ids = set(documentos_existentes.values())
    historicos_documentos = list(
        Documento.history.filter(contrato_id=contrato.pk).select_related("history_user")
    )
    documentos_por_id = {}
    cancelamentos_sistema = {}
    reativacoes_sistema = {}
    for registro in sorted(historicos_documentos, key=_chave_historico):
        documentos_por_id[registro.id] = registro.identificador_base
        motivo = registro.history_change_reason or ""
        if motivo.startswith("cancelamento_sistema:"):
            cancelamentos_sistema.setdefault(motivo, []).append(registro)
        elif motivo.startswith("reativacao_sistema:"):
            reativacoes_sistema.setdefault(motivo, []).append(registro)
        else:
            eventos.append(
                _evento_historico(
                    registro,
                    Documento,
                    entidade="documento",
                    contrato=contrato,
                    codigo=registro.identificador_base,
                    documento_id=registro.id if registro.id in documentos_existentes_ids else None,
                )
            )
    documentos_ids = set(documentos_por_id) | documentos_existentes_ids

    for registro in CodigoDocumento.history.filter(documento_id__in=documentos_ids).select_related("history_user"):
        eventos.append(
            _evento_historico(
                registro,
                CodigoDocumento,
                entidade="código do documento",
                contrato=contrato,
                codigo=documentos_por_id.get(registro.documento_id, ""),
                documento_id=registro.documento_id if registro.documento_id in documentos_existentes_ids else None,
            )
        )

    historicos_emissoes = list(
        Emissao.history.filter(documento_id__in=documentos_ids).select_related("history_user")
    )
    emissao_documentos = {}
    for registro in sorted(historicos_emissoes, key=_chave_historico):
        emissao_documentos[registro.id] = registro.documento_id
        eventos.append(
            _evento_historico(
                registro,
                Emissao,
                entidade="emissão",
                contrato=contrato,
                codigo=documentos_por_id.get(registro.documento_id, ""),
                documento_id=registro.documento_id if registro.documento_id in documentos_existentes_ids else None,
            )
        )
    emissoes_ids = set(emissao_documentos)
    emissoes_ids.update(
        Emissao.objects.filter(documento_id__in=documentos_ids).values_list("pk", flat=True)
    )

    for modelo, filtro, entidade, codigo_resolver in (
        (Analise, {"emissao_id__in": emissoes_ids}, "análise", lambda r: documentos_por_id.get(emissao_documentos.get(r.emissao_id), "")),
        (PerfilContrato, {"contrato_id": contrato.pk}, "perfil do contrato", lambda r: ""),
        (IndiceDocumentos, {"contrato_id": contrato.pk}, "índice de documentos", lambda r: ""),
        (
            InconsistenciaImportacao,
            {"importacao_id__contrato": contrato.pk},
            "inconsistência de importação",
            lambda r: r.codigo_lido,
        ),
    ):
        for registro in modelo.history.filter(**filtro).select_related("history_user"):
            documento_id = None
            if modelo is Analise:
                documento_id = emissao_documentos.get(registro.emissao_id)
            elif modelo is InconsistenciaImportacao:
                documento_id = documentos_existentes.get(registro.codigo_lido)
            if documento_id not in documentos_existentes_ids:
                documento_id = None
            eventos.append(
                _evento_historico(
                    registro,
                    modelo,
                    entidade=entidade,
                    contrato=contrato,
                    codigo=codigo_resolver(registro),
                    documento_id=documento_id,
                )
            )

    for registro in InconsistenciaImportacao.history.filter(
        importacao_situacao__contrato=contrato
    ).select_related("history_user"):
        eventos.append(
            _evento_historico(
                registro,
                InconsistenciaImportacao,
                entidade="inconsistência de importação",
                contrato=contrato,
                codigo=registro.codigo_lido,
                documento_id=documentos_existentes.get(registro.codigo_lido),
            )
        )

    indices_ids = set(
        IndiceDocumentos.history.filter(contrato_id=contrato.pk).values_list("id", flat=True)
    )
    indices_ids.update(
        IndiceDocumentos.objects.filter(contrato=contrato).values_list("pk", flat=True)
    )
    for registro in ItemPrevisto.history.filter(indice_id__in=indices_ids).select_related("history_user"):
        eventos.append(
            _evento_historico(
                registro,
                ItemPrevisto,
                entidade="item previsto",
                contrato=contrato,
                codigo=documentos_por_id.get(registro.documento_id, ""),
                documento_id=registro.documento_id if registro.documento_id in documentos_existentes_ids else None,
            )
        )

    for registro in PrevisaoEmissao.history.filter(contrato_id=contrato.pk).select_related("history_user"):
        eventos.append(
            _evento_historico(
                registro,
                PrevisaoEmissao,
                entidade="previsão de emissão",
                contrato=contrato,
                codigo=documentos_por_id.get(registro.documento_id, ""),
                documento_id=registro.documento_id if registro.documento_id in documentos_existentes_ids else None,
            )
        )

    for registro in FotoPainel.history.filter(contrato_id=contrato.pk).select_related(
        "history_user", "criado_por"
    ):
        eventos.append(_evento_foto_painel(registro))

    eventos.extend(
        _evento_cancelamento_sistema(registros, contrato)
        for registros in cancelamentos_sistema.values()
    )
    eventos.extend(
        _evento_reativacao_sistema(registros, contrato)
        for registros in reativacoes_sistema.values()
    )
    eventos.extend(_eventos_importacao(contrato))
    return sorted(
        (evento for evento in eventos if not evento.get("agrupar_no_evento")),
        key=lambda evento: (evento["data_hora"], evento["chave"]),
        reverse=True,
    )


def _eventos_importacao(contrato):
    eventos = []
    for registro in ImportacaoID.objects.filter(contrato=contrato).select_related("importado_por", "indice"):
        evento = _evento_importacao(
                registro,
                chave=f"importacao-id-{registro.pk}",
                tipo="id",
                titulo="Importação de ID",
                resumo=(
                    f"importou ID {registro.arquivo_nome}: {registro.linhas_validas} válidas, "
                    f"{registro.linhas_invalidas} recusadas"
                ),
                validas=registro.linhas_validas,
                recusadas=registro.linhas_invalidas,
                detalhes=[
                    ("Arquivo", registro.arquivo_nome),
                    ("Índice", f"{registro.indice.codigo}, revisão {registro.indice.revisao}"),
                    ("Linhas válidas", registro.linhas_validas),
                    ("Linhas recusadas", registro.linhas_invalidas),
                ],
            )
        _anexar_historico_agrupado(evento, f"importacao_id:{registro.pk}")
        eventos.append(evento)
    for registro in ImportacaoSituacao.objects.filter(contrato=contrato).select_related("importado_por"):
        situacao_padrao = registro.arquivo_nome.startswith(_PREFIXO_SITUACAO_PADRAO)
        arquivo_nome = (
            registro.arquivo_nome[len(_PREFIXO_SITUACAO_PADRAO):]
            if situacao_padrao
            else registro.arquivo_nome
        )
        tipo_situacao = "situação pela planilha padrão" if situacao_padrao else "situação do PW"
        evento = _evento_importacao(
                registro,
                chave=f"importacao-situacao-{registro.pk}",
                tipo=tipo_situacao,
                titulo=f"Importação de {tipo_situacao}",
                resumo=(
                    f"importou {tipo_situacao} {arquivo_nome}: {registro.documentos} documentos, "
                    f"{registro.emissoes} emissões, "
                    f"{registro.analises_explicitas + registro.analises_deduzidas} análises, "
                    f"{registro.linhas_invalidas} recusadas"
                ),
                validas=registro.documentos,
                recusadas=registro.linhas_invalidas,
                detalhes=[
                    ("Arquivo", arquivo_nome),
                    ("Data da extração", registro.data_extracao),
                    ("Documentos", registro.documentos),
                    ("Emissões", registro.emissoes),
                    ("Análises explícitas", registro.analises_explicitas),
                    ("Análises deduzidas", registro.analises_deduzidas),
                    ("Linhas recusadas", registro.linhas_invalidas),
                ],
            )
        motivo_historico = "importacao_situacao_padrao" if situacao_padrao else "importacao_situacao"
        _anexar_historico_agrupado(evento, f"{motivo_historico}:{registro.pk}")
        codigos_cancelados = [] if situacao_padrao else _codigos_cancelados_pw(registro)
        if codigos_cancelados:
            evento["detalhes"].append(
                {
                    "campo": "Cancelados pelo PW",
                    "antes": "",
                    "depois": (
                        f"{len(codigos_cancelados)} documentos cancelados pelo PW: "
                        f"{', '.join(codigos_cancelados)}"
                    ),
                }
            )
        eventos.append(evento)
    for registro in ImportacaoCronograma.objects.filter(contrato=contrato).select_related("importado_por"):
        eventos.append(
            _evento_importacao(
                registro,
                chave=f"importacao-cronograma-{registro.pk}",
                tipo="cronograma",
                titulo="Importação de cronograma",
                resumo=(
                    f"importou cronograma {registro.arquivo_nome}: {registro.linhas_validas} válidas, "
                    f"{registro.linhas_recusadas} recusadas"
                ),
                validas=registro.linhas_validas,
                recusadas=registro.linhas_recusadas,
                detalhes=[
                    ("Arquivo", registro.arquivo_nome),
                    ("Linhas válidas", registro.linhas_validas),
                    ("Linhas recusadas", registro.linhas_recusadas),
                ],
            )
        )
    reprocessamentos = ReprocessamentoImportacao.objects.filter(
        Q(importacao_id__contrato=contrato)
        | Q(importacao_situacao__contrato=contrato)
    ).select_related("reprocessado_por", "importacao_id__indice", "importacao_situacao")
    for registro in reprocessamentos:
        evento = _evento_reprocessamento(registro)
        _anexar_historico_agrupado(evento, f"reprocessamento:{registro.pk}")
        eventos.append(evento)
    return eventos


def _evento_cancelamento_sistema(registros, contrato):
    registros = sorted(registros, key=_chave_historico)
    documento_ids = {registro.id for registro in registros}
    codigos = {registro.identificador_base for registro in registros}
    codigos.update(
        CodigoDocumento.objects.filter(documento_id__in=documento_ids).values_list("codigo", flat=True)
    )
    codigos = sorted(codigo for codigo in codigos if codigo)
    ultimo = registros[-1]
    ator = _ator_historico(ultimo)
    nome = _nome_usuario(ator)
    motivo = _rotulo_motivo_cancelamento(contrato, ultimo.motivo_cancelamento)
    detalhes = [
        {"campo": "Quantidade", "antes": "", "depois": len(registros)},
        {"campo": "Motivo", "antes": "", "depois": motivo},
        {"campo": "Códigos", "antes": "", "depois": ", ".join(codigos)},
    ]
    if ultimo.motivo_cancelamento_obs:
        detalhes.append(
            {"campo": "Observação", "antes": "", "depois": ultimo.motivo_cancelamento_obs}
        )
    return {
        "chave": f"cancelamento-sistema-{ultimo.history_change_reason.partition(':')[2]}",
        "data_hora": _localizar(max(registro.history_date for registro in registros)),
        "acao": "cancelou",
        "acao_rotulo": "Cancelou",
        "entidade": "Cancelamento de documentos",
        "tipo_importacao": "",
        "codigo": ", ".join(codigos),
        "codigos": codigos,
        "usuario": ator,
        "usuario_id": getattr(ator, "pk", None),
        "usuario_nome": nome,
        "resumo": f"Cancelado por {nome} · {motivo}",
        "detalhes": detalhes,
        "validas": len(registros),
        "recusadas": None,
        "documento_id": None,
        "contrato_id": contrato.pk,
        "link_recusadas": False,
        "agrupar_no_evento": False,
    }


def _evento_reativacao_sistema(registros, contrato):
    registros = sorted(registros, key=_chave_historico)
    documento_ids = {registro.id for registro in registros}
    codigos = {registro.identificador_base for registro in registros}
    codigos.update(
        CodigoDocumento.objects.filter(documento_id__in=documento_ids).values_list("codigo", flat=True)
    )
    codigos = sorted(codigo for codigo in codigos if codigo)
    ultimo = registros[-1]
    ator = _ator_historico(ultimo)
    nome = _nome_usuario(ator)
    observacao = ultimo.observacao_reativacao
    detalhes = [
        {"campo": "Quantidade", "antes": "", "depois": len(registros)},
        {"campo": "Códigos", "antes": "", "depois": ", ".join(codigos)},
    ]
    if observacao:
        detalhes.append({"campo": "Motivo da reativação", "antes": "", "depois": observacao})
    return {
        "chave": f"reativacao-sistema-{ultimo.history_change_reason.partition(':')[2]}",
        "data_hora": _localizar(max(registro.history_date for registro in registros)),
        "acao": "reativou",
        "acao_rotulo": "Reativou",
        "entidade": "Reativação de documentos",
        "tipo_importacao": "",
        "codigo": ", ".join(codigos),
        "codigos": codigos,
        "usuario": ator,
        "usuario_id": getattr(ator, "pk", None),
        "usuario_nome": nome,
        "resumo": f"Reativado por {nome}" + (f" · {observacao}" if observacao else ""),
        "detalhes": detalhes,
        "validas": len(registros),
        "recusadas": None,
        "documento_id": None,
        "contrato_id": contrato.pk,
        "link_recusadas": False,
        "agrupar_no_evento": False,
    }


def _rotulo_motivo_cancelamento(contrato, identificador):
    perfil_modelo = PerfilContrato.perfil_vigente(contrato, timezone.localdate())
    if perfil_modelo is None:
        return identificador or "Não informado"
    try:
        perfil = perfil_de_dict(perfil_modelo.definicao)
    except ErroPerfil:
        return identificador or "Não informado"
    return next(
        (motivo.rotulo for motivo in perfil.cancelamento.motivos if motivo.id == identificador),
        identificador or "Não informado",
    )


def _codigos_cancelados_pw(registro):
    perfil_modelo = PerfilContrato.perfil_vigente(registro.contrato, registro.data_extracao)
    if perfil_modelo is None:
        return []
    try:
        perfil = perfil_de_dict(perfil_modelo.definicao)
    except ErroPerfil:
        return []

    motivo = f"importacao_situacao:{registro.pk}"
    analises = Analise.history.filter(history_change_reason=motivo).order_by(
        "history_date", "history_id"
    )
    emissoes_canceladas = {
        analise.emissao_id
        for analise in analises
        if classificar(perfil, analise.situacao).id.casefold() == "cancelado"
    }
    documento_ids = set(
        Emissao.objects.filter(pk__in=emissoes_canceladas).values_list("documento_id", flat=True)
    )
    if not documento_ids:
        return []

    codigos = set(
        CodigoDocumento.objects.filter(
            documento_id__in=documento_ids,
            perfil=perfil_modelo,
        ).values_list("codigo", flat=True)
    )
    codigos.update(
        Documento.objects.filter(pk__in=documento_ids).values_list("identificador_base", flat=True)
    )
    return sorted(codigo for codigo in codigos if codigo)


def _evento_importacao(registro, *, chave, tipo, titulo, resumo, validas, recusadas, detalhes):
    return {
        "chave": chave,
        "data_hora": _localizar(registro.importado_em),
        "acao": "importou",
        "acao_rotulo": "Importou",
        "entidade": titulo,
        "tipo_importacao": tipo,
        "codigo": "",
        "usuario": registro.importado_por,
        "usuario_id": registro.importado_por_id,
        "usuario_nome": _nome_usuario(registro.importado_por),
        "resumo": f"{_nome_usuario(registro.importado_por)} {resumo}",
        "detalhes": [{"campo": campo, "antes": "", "depois": _formatar(valor)} for campo, valor in detalhes],
        "validas": validas,
        "recusadas": recusadas,
        "importacao_id": registro.pk,
        "link_recusadas": recusadas > 0,
        "agrupar_no_evento": False,
    }


def _evento_foto_painel(registro):
    ator = _ator_historico(registro)
    nome = _nome_usuario(ator)
    anterior = registro.prev_record
    numeros_anteriores = anterior.numeros if anterior is not None else {}
    rotulos = (
        ("avanco_percentual", "Avanço (%)"),
        ("previstos", "Previstos"),
        ("emitidos", "Emitidos"),
        ("aprovados", "Aprovados"),
        ("em_analise", "Em análise"),
        ("pendentes", "Pendentes"),
        ("cancelados", "Cancelados"),
        ("pendencias_abertas", "Pendências abertas"),
        ("atrasos_cliente", "Atrasos cliente"),
        ("atrasos_nossos", "Atrasos nossos"),
    )
    detalhes = [
        {"campo": "Data", "antes": "", "depois": _formatar(registro.data)},
    ]
    for campo, rotulo in rotulos:
        antes = numeros_anteriores.get(campo)
        depois = registro.numeros.get(campo)
        if anterior is None or antes != depois:
            detalhes.append(
                {
                    "campo": rotulo,
                    "antes": _formatar(antes) if anterior is not None else "",
                    "depois": _formatar(depois),
                }
            )
    verbo = {"+": "criou", "~": "alterou", "-": "excluiu"}.get(
        registro.history_type, "alterou"
    )
    return {
        "chave": f"historico-fotopainel-{registro.history_id}",
        "data_hora": _localizar(registro.history_date),
        "acao": verbo,
        "acao_rotulo": "Foto do Painel guardada",
        "entidade": "foto do Painel",
        "tipo_importacao": "",
        "codigo": "",
        "usuario": ator,
        "usuario_id": getattr(ator, "pk", None),
        "usuario_nome": nome,
        "resumo": f"{nome} · Foto do Painel guardada em {registro.data:%d/%m/%Y}",
        "detalhes": detalhes,
        "validas": None,
        "recusadas": None,
        "link_recusadas": False,
        "agrupar_no_evento": False,
    }


def _evento_historico(registro, modelo, *, entidade, contrato, codigo, documento_id=None):
    acao = {"+": "criou", "~": "alterou", "-": "excluiu"}.get(registro.history_type, "alterou")
    detalhes = _diferencas(registro, modelo) if acao == "alterou" else []
    ator = _ator_historico(registro)
    nome = _nome_usuario(ator)
    descricao = _descricao_historico(registro, entidade, acao, codigo, detalhes)
    resumo = f"{nome} {descricao}"
    alterou_titulo = (
        modelo is Documento
        and acao == "alterou"
        and any(item["campo"] == "título" for item in detalhes)
        and bool(registro.history_change_reason)
    )
    acao_rotulo = dict(ACOES).get(acao, acao.title())
    if alterou_titulo:
        detalhe_titulo = next(item for item in detalhes if item["campo"] == "título")
        detalhe_titulo["campo"] = "Título"
        detalhes.append(
            {
                "campo": "Motivo",
                "antes": "",
                "depois": registro.history_change_reason,
            }
        )
        acao_rotulo = "Título alterado"
        resumo = (
            f"{nome} · Título alterado em {codigo}: "
            f"{detalhe_titulo['antes']} → {detalhe_titulo['depois']}"
        )
    resumo_antes_codigo, separador, resumo_depois_codigo = resumo.partition(codigo) if codigo else ("", "", "")
    return {
        "chave": f"historico-{modelo._meta.model_name}-{registro.history_id}",
        "data_hora": _localizar(registro.history_date),
        "acao": acao,
        "acao_rotulo": acao_rotulo,
        "entidade": entidade,
        "tipo_importacao": "",
        "codigo": codigo or "",
        "usuario": ator,
        "usuario_id": getattr(ator, "pk", None),
        "usuario_nome": nome,
        "resumo": resumo,
        "resumo_antes_codigo": resumo_antes_codigo if separador else None,
        "resumo_depois_codigo": resumo_depois_codigo if separador else None,
        "documento_id": documento_id,
        "detalhes": detalhes,
        "registro_id": registro.pk,
        "contrato_id": contrato.pk,
        "validas": None,
        "recusadas": None,
        "link_recusadas": False,
        "history_change_reason": registro.history_change_reason,
        "agrupar_no_evento": bool(
            registro.history_change_reason
            and registro.history_change_reason.startswith(
                (
                    "importacao_id:",
                    "importacao_situacao:",
                    "importacao_situacao_padrao:",
                    "reprocessamento:",
                )
            )
        ),
    }


def _evento_reprocessamento(registro):
    if registro.importacao_id_id:
        tipo = "ID"
        importacao = registro.importacao_id
        lote = f"ID {importacao.indice.codigo}, revisão {importacao.indice.revisao}"
        recusadas = importacao.linhas_invalidas
        importacao_id = importacao.pk
    else:
        tipo = "situação do PW"
        importacao = registro.importacao_situacao
        lote = f"situação do PW {importacao.arquivo_nome}"
        recusadas = importacao.linhas_invalidas
        importacao_id = importacao.pk
    nome = _nome_usuario(registro.reprocessado_por)
    codigos = registro.codigos or []
    codigo_filtro = ", ".join(codigos)
    resumo = (
        f"{nome} reprocessou {registro.linhas_validas} linha(s) em {lote}"
    )
    detalhes = [
        ("Lote original", lote),
        ("Linhas que passaram a valer", registro.linhas_validas),
        ("Códigos reprocessados", ", ".join(codigos) if codigos else "—"),
    ]
    return {
        "chave": f"reprocessamento-{registro.pk}",
        "data_hora": _localizar(registro.reprocessado_em),
        "acao": "reprocessou",
        "acao_rotulo": "Reprocessou",
        "entidade": f"Reprocessamento de {tipo}",
        "tipo_importacao": tipo.casefold(),
        "codigo": codigo_filtro,
        "codigos": codigos,
        "usuario": registro.reprocessado_por,
        "usuario_id": registro.reprocessado_por_id,
        "usuario_nome": nome,
        "resumo": resumo,
        "detalhes": [
            {"campo": campo, "antes": "", "depois": _formatar(valor)}
            for campo, valor in detalhes
        ],
        "validas": registro.linhas_validas,
        "recusadas": recusadas,
        "importacao_id": importacao_id,
        "link_recusadas": recusadas > 0,
        "agrupar_no_evento": False,
    }


def _anexar_historico_agrupado(evento, motivo):
    historicos = []
    modelos = (
        Documento,
        CodigoDocumento,
        Emissao,
        Analise,
        IndiceDocumentos,
        ItemPrevisto,
        PrevisaoEmissao,
        InconsistenciaImportacao,
    )
    for modelo in modelos:
        historicos.extend(
            (modelo, historico)
            for historico in modelo.history.filter(history_change_reason=motivo)
        )
    if not historicos:
        return

    nomes = {
        Documento: "documento",
        CodigoDocumento: "código",
        Emissao: "emissão",
        Analise: "análise",
        IndiceDocumentos: "índice",
        ItemPrevisto: "item previsto",
        PrevisaoEmissao: "previsão de emissão",
        InconsistenciaImportacao: "inconsistência",
    }
    plurais = {
        "documento": "documentos",
        "código": "códigos",
        "emissão": "emissões",
        "análise": "análises",
        "índice": "índices",
        "item previsto": "itens previstos",
        "previsão de emissão": "previsões de emissão",
        "inconsistência": "inconsistências",
    }
    verbos = {"+": "criou", "~": "alterou", "-": "excluiu"}
    contagens = {}
    codigos = set(evento.get("codigos", ()))
    documentos_ids = set()
    for modelo, historico in historicos:
        nome = nomes.get(modelo)
        if nome:
            verbo = verbos.get(historico.history_type, "alterou")
            contagens[(verbo, nome)] = contagens.get((verbo, nome), 0) + 1
        for campo in ("codigo_lido", "codigo", "identificador_base"):
            valor = getattr(historico, campo, None)
            if valor and modelo not in (IndiceDocumentos,):
                codigos.add(str(valor))
        documento_id = getattr(historico, "documento_id", None)
        if documento_id:
            documentos_ids.add(documento_id)
    if documentos_ids:
        codigos.update(
            Documento.objects.filter(pk__in=documentos_ids).values_list("identificador_base", flat=True)
        )

    frases = []
    for (verbo, nome), quantidade in sorted(contagens.items()):
        substantivo = nome if quantidade == 1 else plurais[nome]
        frases.append(f"{verbo} {quantidade} {substantivo}")
    if frases:
        evento["detalhes"].append(
            {
                "campo": "Alterações agrupadas",
                "antes": "",
                "depois": "; ".join(frases),
            }
        )
    if codigos:
        codigos_ordenados = sorted(codigos)
        evento["codigos"] = codigos_ordenados
        evento["codigo"] = ", ".join(codigos_ordenados)
        evento["detalhes"].append(
            {
                "campo": "Códigos",
                "antes": "",
                "depois": ", ".join(codigos_ordenados),
            }
        )


def _diferencas(registro, modelo):
    anterior = registro.prev_record
    if anterior is None:
        return []
    delta = registro.diff_against(anterior)
    diferencas = []
    for mudanca in delta.changes:
        campo = mudanca.field
        try:
            metadado = modelo._meta.get_field(campo)
            rotulo = str(metadado.verbose_name)
        except Exception:
            metadado = None
            rotulo = campo.replace("_", " ")
        diferencas.append(
            {
                "campo": rotulo,
                "antes": _valor_diferenca(mudanca.old, metadado),
                "depois": _valor_diferenca(mudanca.new, metadado),
            }
        )
    return diferencas


def _valor_diferenca(valor, campo):
    if campo is not None and campo.is_relation and valor is not None:
        try:
            objeto = campo.related_model.objects.filter(pk=valor).first()
            if objeto is not None:
                return str(objeto)
        except (TypeError, ValueError):
            pass
    return _formatar(valor)


def _descricao_historico(registro, entidade, acao, codigo, detalhes):
    artigo = {
        "documento": "o documento",
        "emissão": "a emissão",
        "análise": "a análise",
        "perfil do contrato": "o perfil do contrato",
        "índice de documentos": "o índice de documentos",
        "item previsto": "o item previsto",
        "previsão de emissão": "a previsão de emissão",
        "código do documento": "o código do documento",
        "inconsistência de importação": "a inconsistência de importação",
    }.get(entidade, entidade)
    if acao == "criou":
        if codigo:
            return f"criou {artigo} {codigo}"
        return f"criou {artigo}"
    if acao == "excluiu":
        if codigo:
            return f"excluiu {artigo} {codigo}"
        return f"excluiu {artigo}"
    if entidade == "documento" and any(item["campo"] == "título" for item in detalhes):
        return f"alterou o título de {codigo}"
    if entidade == "código do documento":
        return f"alterou o código de {codigo}"
    if codigo:
        return f"alterou {artigo} de {codigo}"
    if entidade == "índice de documentos":
        return f"alterou {artigo} {registro.codigo}, revisão {registro.revisao}"
    if entidade == "perfil do contrato":
        return f"alterou o perfil do contrato, versão {registro.versao}"
    return f"alterou {artigo}"


def _chave_historico(registro):
    return registro.history_date, registro.history_id


def _nome_usuario(usuario):
    if usuario is None:
        return "Sistema"
    return usuario.get_full_name() or usuario.get_username()


def _ator_historico(registro):
    usuario = registro.history_user
    if usuario is not None:
        return usuario
    for campo in (
        "criado_por",
        "registrado_por",
        "importado_por",
        "resolvida_por",
        "cancelado_por",
    ):
        usuario_id = getattr(registro, f"{campo}_id", None)
        if usuario_id:
            return get_user_model().objects.filter(pk=usuario_id).first()
    return None


def _localizar(valor):
    if timezone.is_aware(valor):
        return timezone.localtime(valor)
    return timezone.make_aware(valor)


def _formatar(valor):
    if valor is None:
        return "—"
    if isinstance(valor, datetime):
        return timezone.localtime(valor).strftime("%d/%m/%Y %H:%M") if timezone.is_aware(valor) else valor.strftime("%d/%m/%Y %H:%M")
    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, (dict, list)):
        return json.dumps(valor, ensure_ascii=False, sort_keys=True)
    return str(valor)
