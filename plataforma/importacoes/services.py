from django.db import transaction
from django.utils import timezone
from uuid import uuid4

from core.perfil import ErroPerfil, perfil_de_dict
from core.perfil.codigo import ErroCodigo, interpretar
from documentos.models import CodigoDocumento, Documento

from .id_excel import PreviaID
from .models import (
    InconsistenciaImportacao,
    ImportacaoID,
    IndiceDocumentos,
    ItemPrevisto,
    ReprocessamentoImportacao,
)


class ErroAplicacaoID(ValueError):
    pass


@transaction.atomic
def aplicar_previa(
    previa: PreviaID,
    *,
    contrato,
    perfil_modelo,
    usuario=None,
    inconsistencias_existentes=None,
    substituir_ids=(),
):
    """Aplica uma prévia validada de forma atômica e idempotente."""
    reprocessamento = inconsistencias_existentes is not None
    inconsistencias_existentes = list(inconsistencias_existentes or ())
    if previa.contrato_id != contrato.pk or perfil_modelo.contrato_id != contrato.pk:
        raise ErroAplicacaoID("A prévia, o perfil e o contrato precisam ser os mesmos.")
    if previa.perfil_id != perfil_modelo.pk:
        raise ErroAplicacaoID("O perfil vigente mudou. Gere uma nova prévia antes de confirmar.")
    substituir_ids = tuple(int(pk) for pk in substituir_ids)
    if len(set(substituir_ids)) != len(substituir_ids):
        raise ErroAplicacaoID("A prévia contém IDs substituídos repetidos. Gere uma nova prévia.")
    if substituir_ids:
        if previa.fonte != IndiceDocumentos.Fonte.EXCEL_ID:
            raise ErroAplicacaoID("A substituição está disponível apenas para IDs importados por Excel.")
        if any(linha.categoria in {"codigos_invalidos", "atributos_divergentes", "linhas_ilegiveis"} for linha in previa.linhas):
            raise ErroAplicacaoID(
                "Corrija as linhas recusadas antes de substituir um ID vigente. Gere uma nova prévia."
            )
        indices_substituidos = list(
            IndiceDocumentos.objects.select_for_update().filter(
                pk__in=substituir_ids,
                contrato=contrato,
                fonte=IndiceDocumentos.Fonte.EXCEL_ID,
                vigente=True,
                substituido_por__isnull=True,
            ).order_by("pk")
        )
        if len(indices_substituidos) != len(substituir_ids):
            raise ErroAplicacaoID(
                "Um ID selecionado não está mais vigente ou não pertence a este contrato. Gere nova prévia."
            )
    else:
        indices_substituidos = []
    problemáticas = [
        linha for linha in previa.linhas
        if linha.categoria in {"codigos_invalidos", "atributos_divergentes", "linhas_ilegiveis"}
    ]
    linhas_validas = [linha for linha in previa.linhas if linha.identificador_base]
    if not linhas_validas and not problemáticas:
        raise ErroAplicacaoID("A prévia não contém linhas para importar.")
    try:
        perfil_validado = perfil_de_dict(perfil_modelo.definicao)
    except ErroPerfil as erro:
        raise ErroAplicacaoID(f"O perfil vigente não pode interpretar códigos: {erro}") from erro

    chave = {
        "contrato": contrato,
        "fonte": previa.fonte,
        "codigo": previa.codigo_indice,
        "revisao": previa.revisao,
    }
    indice = IndiceDocumentos.objects.filter(**chave).first()
    if indice is not None and indice.pk in substituir_ids:
        raise ErroAplicacaoID("Um ID não pode substituir a si mesmo.")
    agora = timezone.now()
    motivo_historico = f"importacao_id:pendente:{uuid4().hex}"
    if reprocessamento:
        if not inconsistencias_existentes or indice is None:
            raise ErroAplicacaoID("A importação original não está disponível para reprocessamento.")
        if any(
            inconsistencia.importacao_id_id is None
            or inconsistencia.importacao_id.indice_id != indice.pk
            or inconsistencia.importacao_id.contrato_id != contrato.pk
            for inconsistencia in inconsistencias_existentes
        ):
            raise ErroAplicacaoID("As linhas recusadas não pertencem ao índice desta prévia.")
        importacoes_origem = {item.importacao_id_id for item in inconsistencias_existentes}
        if None in importacoes_origem or len(importacoes_origem) != 1:
            raise ErroAplicacaoID("As linhas recusadas precisam pertencer ao mesmo lote original.")
        numeros_validos = {linha.numero_linha for linha in linhas_validas}
        linhas_reprocessadas = [
            item for item in inconsistencias_existentes
            if item.resolvida_em is None and item.numero_linha in numeros_validos
        ]
        codigos_reprocessados = [
            linha.codigo for linha in linhas_validas
            if linha.numero_linha in {item.numero_linha for item in linhas_reprocessadas}
        ]
        evento_reprocessamento = ReprocessamentoImportacao.objects.create(
            importacao_id_id=next(iter(importacoes_origem)),
            reprocessado_por=usuario,
            linhas_validas=len(linhas_reprocessadas),
            codigos=sorted(set(codigos_reprocessados)),
        )
        motivo_historico = f"reprocessamento:{evento_reprocessamento.pk}"
    if indice is None:
        if not problemáticas:
            anteriores = IndiceDocumentos.objects.filter(
                contrato=contrato,
                fonte=previa.fonte,
                codigo=previa.codigo_indice,
                vigente=True,
            )
            for anterior in anteriores:
                anterior.vigente = False
                _marcar_historico(anterior, usuario, motivo_historico)
                anterior.save(update_fields=("vigente",))
        indice = IndiceDocumentos(
            **chave,
            arquivo_nome=previa.arquivo_nome,
            importado_em=agora,
            importado_por=usuario,
        )
        _marcar_historico(indice, usuario, motivo_historico)
        indice.save()
    elif not reprocessamento:
        campos_alterados = []
        if indice.arquivo_nome != previa.arquivo_nome:
            indice.arquivo_nome = previa.arquivo_nome
            campos_alterados.append("arquivo_nome")
        if indice.importado_por_id != getattr(usuario, "pk", None):
            indice.importado_por = usuario
            campos_alterados.append("importado_por")
        if campos_alterados:
            _marcar_historico(indice, usuario, motivo_historico)
            indice.save(update_fields=campos_alterados)
        if not problemáticas:
            anteriores = IndiceDocumentos.objects.filter(
                contrato=contrato,
                fonte=previa.fonte,
                codigo=previa.codigo_indice,
                vigente=True,
            ).exclude(pk=indice.pk)
            for anterior in anteriores:
                anterior.vigente = False
                _marcar_historico(anterior, usuario, motivo_historico)
                anterior.save(update_fields=("vigente",))
            if not indice.vigente:
                indice.vigente = True
                _marcar_historico(indice, usuario, motivo_historico)
                indice.save(update_fields=("vigente",))

    if not reprocessamento:
        importacao = ImportacaoID.objects.create(
            contrato=contrato,
            indice=indice,
            arquivo_nome=previa.arquivo_nome,
            importado_por=usuario,
            linhas_validas=len(linhas_validas),
            linhas_invalidas=len(problemáticas),
        )
        motivo_importacao = f"importacao_id:{importacao.pk}"
        IndiceDocumentos.history.filter(
            history_change_reason=motivo_historico
        ).update(history_change_reason=motivo_importacao)
        motivo_historico = motivo_importacao
        for linha in problemáticas:
            inconsistencia = InconsistenciaImportacao(
                importacao_id=importacao,
                numero_linha=linha.numero_linha,
                codigo_lido=linha.codigo,
                categoria=linha.categoria,
                campo_falhou=linha.campo_falhou,
                caixa_falhou=linha.caixa_falhou or linha.campo_falhou,
                mensagem=linha.mensagem or "Linha não importada por ser inválida.",
                dados_linha=linha.dados_linha or {},
            )
            _marcar_historico(inconsistencia, usuario, motivo_historico)
            inconsistencia.save()
        codigos_importados = {
            linha.codigo.strip().upper()
            for linha in linhas_validas
            if linha.codigo.strip()
        }
        if codigos_importados:
            recusas_anteriores = InconsistenciaImportacao.objects.filter(
                importacao_id__contrato=contrato,
                importacao_id__indice__fonte=previa.fonte,
                resolvida_em__isnull=True,
            ).exclude(importacao_id=importacao)
            for inconsistencia in recusas_anteriores:
                if inconsistencia.codigo_lido.strip().upper() in codigos_importados:
                    inconsistencia.resolvida_em = agora
                    inconsistencia.resolvida_por = usuario
                    _marcar_historico(inconsistencia, usuario, motivo_historico)
                    inconsistencia.save(update_fields=("resolvida_em", "resolvida_por"))

    documentos_incluidos = set()
    for linha in linhas_validas:
        if not linha.identificador_base or linha.segmentos is None:
            continue
        interpretado = interpretar(perfil_validado, linha.codigo)
        if isinstance(interpretado, ErroCodigo) or (
            interpretado.identificador_base != linha.identificador_base
            or dict(interpretado.segmentos) != linha.segmentos
        ):
            raise ErroAplicacaoID("Um código da prévia não corresponde ao perfil vigente.")
        documento = Documento.objects.filter(
            contrato=contrato,
            identificador_base=linha.identificador_base,
        ).first()
        if documento is None:
            documento = Documento(
                contrato=contrato,
                identificador_base=linha.identificador_base,
            )
            documento.tipo = linha.segmentos.get("tipo", "")
            documento.trecho = linha.segmentos.get("trecho", "")
            documento.disciplina = linha.segmentos.get("disciplina", "")
            documento.atributos = dict(linha.segmentos)
            documento.titulo = linha.titulo
            _marcar_historico(documento, usuario, motivo_historico)
            documento.save()
        else:
            alteracoes = {
                "tipo": linha.segmentos.get("tipo", ""),
                "trecho": linha.segmentos.get("trecho", ""),
                "disciplina": linha.segmentos.get("disciplina", ""),
                "atributos": dict(linha.segmentos),
                "titulo": linha.titulo,
                "fora_do_id": False,
            }
            campos_alterados = [
                nome for nome, valor in alteracoes.items()
                if getattr(documento, nome) != valor
            ]
            if campos_alterados:
                for nome in campos_alterados:
                    setattr(documento, nome, alteracoes[nome])
                _marcar_historico(documento, usuario, motivo_historico)
                documento.save(update_fields=campos_alterados)

        codigo = CodigoDocumento.objects.filter(documento=documento, perfil=perfil_modelo).first()
        if codigo is None:
            codigo = CodigoDocumento(
                documento=documento,
                perfil=perfil_modelo,
                codigo=linha.codigo,
            )
            _marcar_historico(codigo, usuario, motivo_historico)
            codigo.save()
        elif codigo.codigo != linha.codigo:
            codigo.codigo = linha.codigo
            _marcar_historico(codigo, usuario, motivo_historico)
            codigo.save(update_fields=("codigo",))

        item = ItemPrevisto.objects.filter(indice=indice, documento=documento).first()
        if item is None:
            item = ItemPrevisto(
                indice=indice,
                documento=documento,
                titulo=linha.titulo,
                excluido=linha.excluido,
            )
            _marcar_historico(item, usuario, motivo_historico)
            item.save()
        elif item.titulo != linha.titulo or item.excluido != linha.excluido:
            item.titulo = linha.titulo
            item.excluido = linha.excluido
            _marcar_historico(item, usuario, motivo_historico)
            item.save(update_fields=("titulo", "excluido"))
        documentos_incluidos.add(documento.pk)

    if reprocessamento:
        numeros_validos = {linha.numero_linha for linha in linhas_validas}
        linhas_por_numero = {linha.numero_linha: linha for linha in previa.linhas}
        for inconsistencia in inconsistencias_existentes:
            linha = linhas_por_numero.get(inconsistencia.numero_linha)
            if linha is None or inconsistencia.resolvida_em is not None:
                continue
            if inconsistencia.numero_linha in numeros_validos:
                inconsistencia.resolvida_em = agora
                inconsistencia.resolvida_por = usuario
                _marcar_historico(inconsistencia, usuario, motivo_historico)
                inconsistencia.save(update_fields=("resolvida_em", "resolvida_por"))
                continue
            campos = {
                "codigo_lido": linha.codigo,
                "categoria": linha.categoria,
                "campo_falhou": linha.campo_falhou,
                "caixa_falhou": linha.caixa_falhou or linha.campo_falhou,
                "mensagem": linha.mensagem or "Linha não importada por ser inválida.",
                "dados_linha": linha.dados_linha or {},
            }
            alterados = []
            for nome, valor in campos.items():
                if getattr(inconsistencia, nome) != valor:
                    setattr(inconsistencia, nome, valor)
                    alterados.append(nome)
            if alterados:
                _marcar_historico(inconsistencia, usuario, motivo_historico)
                inconsistencia.save(update_fields=alterados)
    elif not problemáticas:
        itens_removidos = indice.itens.exclude(documento_id__in=documentos_incluidos).select_related("documento")
        for item in itens_removidos:
            _marcar_historico(item, usuario, motivo_historico)
            item.delete()

    for anterior in indices_substituidos:
        anterior.vigente = False
        anterior.substituido_por = indice
        _marcar_historico(
            anterior,
            usuario,
            f"{motivo_historico}:substituido_por:{indice.pk}",
        )
        anterior.save(update_fields=("vigente", "substituido_por"))

    return indice


def resumir_substituicao(previa, indices_substituidos):
    """Compara os documentos contáveis do novo ID com os IDs marcados na prévia."""
    indices_substituidos = list(indices_substituidos)
    identificadores_novos = {
        linha.identificador_base
        for linha in previa.linhas
        if linha.identificador_base and not linha.excluido
    }
    ids_substituidos = [indice.pk for indice in indices_substituidos]
    previstos_antes = set(
        ItemPrevisto.objects.filter(
            indice__contrato_id=previa.contrato_id,
            indice__vigente=True,
            indice__conta_no_previsto=True,
            excluido=False,
        ).values_list("documento__identificador_base", flat=True)
    )
    previstos_depois = set(
        ItemPrevisto.objects.filter(
            indice__contrato_id=previa.contrato_id,
            indice__vigente=True,
            indice__conta_no_previsto=True,
            excluido=False,
        )
        .exclude(indice_id__in=ids_substituidos)
        .values_list("documento__identificador_base", flat=True)
    ) | identificadores_novos
    continuam = previstos_antes & previstos_depois
    entram = previstos_depois - previstos_antes
    saem = previstos_antes - previstos_depois
    com_movimentacao = set(
        Documento.objects.filter(
            contrato_id=previa.contrato_id,
            identificador_base__in=saem,
            emissoes__isnull=False,
        ).values_list("identificador_base", flat=True).distinct()
    )
    return {
        "continuam": len(continuam),
        "entram": len(entram),
        "saem": len(saem),
        "codigos_que_entram": sorted(entram),
        "codigos_que_saem": sorted(saem),
        "codigos_com_movimentacao": sorted(com_movimentacao),
    }


def previstos_vigentes(contrato):
    """Itens não excluídos que compõem a união dos índices vigentes do contrato."""
    return _previstos_sem_duplicatas(contrato)


def _marcar_historico(instancia, usuario, motivo):
    instancia._history_user = usuario
    instancia._change_reason = motivo


def _previstos_sem_duplicatas(contrato):
    vistos = set()
    for item in (
        ItemPrevisto.objects.filter(
            indice__contrato=contrato,
            indice__vigente=True,
            excluido=False,
        )
        .select_related("documento", "indice")
        .order_by("documento__identificador_base", "indice_id")
    ):
        if item.documento_id not in vistos:
            vistos.add(item.documento_id)
            yield item
