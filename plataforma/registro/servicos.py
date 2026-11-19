import json
from datetime import date, datetime

from django.utils import timezone
from django.contrib.auth import get_user_model

from contratos.models import PerfilContrato
from documentos.models import Analise, CodigoDocumento, Documento, Emissao
from importacoes.models import (
    ImportacaoCronograma,
    ImportacaoID,
    ImportacaoSituacao,
    IndiceDocumentos,
    ItemPrevisto,
    PrevisaoEmissao,
)


ACOES = (
    ("criou", "Criou"),
    ("alterou", "Alterou"),
    ("excluiu", "Excluiu"),
    ("importou", "Importou"),
    ("reprocessou", "Reprocessou"),
)


def carregar_eventos(contrato):
    """Monta uma linha por registro histórico e uma por lote de importação."""
    eventos = []
    historicos_documentos = list(
        Documento.history.filter(contrato_id=contrato.pk).select_related("history_user")
    )
    documentos_por_id = {}
    for registro in sorted(historicos_documentos, key=_chave_historico):
        documentos_por_id[registro.id] = registro.identificador_base
        eventos.append(
            _evento_historico(
                registro,
                Documento,
                entidade="documento",
                contrato=contrato,
                codigo=registro.identificador_base,
            )
        )
    documentos_ids = set(documentos_por_id)
    documentos_ids.update(
        Documento.objects.filter(contrato=contrato).values_list("pk", flat=True)
    )

    for registro in CodigoDocumento.history.filter(documento_id__in=documentos_ids).select_related("history_user"):
        eventos.append(
            _evento_historico(
                registro,
                CodigoDocumento,
                entidade="código do documento",
                contrato=contrato,
                codigo=documentos_por_id.get(registro.documento_id, ""),
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
    ):
        for registro in modelo.history.filter(**filtro).select_related("history_user"):
            eventos.append(
                _evento_historico(
                    registro,
                    modelo,
                    entidade=entidade,
                    contrato=contrato,
                    codigo=codigo_resolver(registro),
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
            )
        )

    eventos.extend(_eventos_importacao(contrato))
    return sorted(eventos, key=lambda evento: (evento["data_hora"], evento["chave"]), reverse=True)


def _eventos_importacao(contrato):
    eventos = []
    for registro in ImportacaoID.objects.filter(contrato=contrato).select_related("importado_por", "indice"):
        eventos.append(
            _evento_importacao(
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
        )
    for registro in ImportacaoSituacao.objects.filter(contrato=contrato).select_related("importado_por"):
        eventos.append(
            _evento_importacao(
                registro,
                chave=f"importacao-situacao-{registro.pk}",
                tipo="situação do PW",
                titulo="Importação de situação do PW",
                resumo=(
                    f"importou situação do PW {registro.arquivo_nome}: {registro.documentos} documentos, "
                    f"{registro.emissoes} emissões, "
                    f"{registro.analises_explicitas + registro.analises_deduzidas} análises, "
                    f"{registro.linhas_invalidas} recusadas"
                ),
                validas=registro.documentos,
                recusadas=registro.linhas_invalidas,
                detalhes=[
                    ("Arquivo", registro.arquivo_nome),
                    ("Data da extração", registro.data_extracao),
                    ("Documentos", registro.documentos),
                    ("Emissões", registro.emissoes),
                    ("Análises explícitas", registro.analises_explicitas),
                    ("Análises deduzidas", registro.analises_deduzidas),
                    ("Linhas recusadas", registro.linhas_invalidas),
                ],
            )
        )
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
    return eventos


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
    }


def _evento_historico(registro, modelo, *, entidade, contrato, codigo):
    acao = {"+": "criou", "~": "alterou", "-": "excluiu"}.get(registro.history_type, "alterou")
    detalhes = _diferencas(registro, modelo) if acao == "alterou" else []
    ator = _ator_historico(registro)
    nome = _nome_usuario(ator)
    descricao = _descricao_historico(registro, entidade, acao, codigo, detalhes)
    return {
        "chave": f"historico-{modelo._meta.model_name}-{registro.history_id}",
        "data_hora": _localizar(registro.history_date),
        "acao": acao,
        "acao_rotulo": dict(ACOES).get(acao, acao.title()),
        "entidade": entidade,
        "tipo_importacao": "",
        "codigo": codigo or "",
        "usuario": ator,
        "usuario_id": getattr(ator, "pk", None),
        "usuario_nome": nome,
        "resumo": f"{nome} {descricao}",
        "detalhes": detalhes,
        "registro_id": registro.pk,
        "contrato_id": contrato.pk,
        "validas": None,
        "recusadas": None,
        "link_recusadas": False,
    }


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
    for campo in ("criado_por", "registrado_por", "importado_por"):
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
