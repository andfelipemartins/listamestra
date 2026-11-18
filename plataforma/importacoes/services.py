from django.db import transaction
from django.utils import timezone

from core.perfil import ErroPerfil, perfil_de_dict
from core.perfil.codigo import ErroCodigo, interpretar
from documentos.models import CodigoDocumento, Documento

from .id_excel import PreviaID
from .models import InconsistenciaImportacao, ImportacaoID, IndiceDocumentos, ItemPrevisto


class ErroAplicacaoID(ValueError):
    pass


@transaction.atomic
def aplicar_previa(previa: PreviaID, *, contrato, perfil_modelo, usuario=None):
    """Aplica uma prévia validada de forma atômica e idempotente."""
    if previa.contrato_id != contrato.pk or perfil_modelo.contrato_id != contrato.pk:
        raise ErroAplicacaoID("A prévia, o perfil e o contrato precisam ser os mesmos.")
    if previa.perfil_id != perfil_modelo.pk:
        raise ErroAplicacaoID("O perfil vigente mudou. Gere uma nova prévia antes de confirmar.")
    problemáticas = [
        linha for linha in previa.linhas
        if linha.categoria in {"codigos_invalidos", "linhas_ilegiveis"}
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
    agora = timezone.now()
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
                anterior._history_user = usuario
                anterior.save(update_fields=("vigente",))
        indice = IndiceDocumentos(
            **chave,
            arquivo_nome=previa.arquivo_nome,
            importado_em=agora,
            importado_por=usuario,
        )
        indice._history_user = usuario
        indice.save()
    else:
        campos_alterados = []
        if indice.arquivo_nome != previa.arquivo_nome:
            indice.arquivo_nome = previa.arquivo_nome
            campos_alterados.append("arquivo_nome")
        if indice.importado_por_id != getattr(usuario, "pk", None):
            indice.importado_por = usuario
            campos_alterados.append("importado_por")
        if campos_alterados:
            indice._history_user = usuario
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
                anterior._history_user = usuario
                anterior.save(update_fields=("vigente",))
            if not indice.vigente:
                indice.vigente = True
                indice._history_user = usuario
                indice.save(update_fields=("vigente",))

    importacao = ImportacaoID.objects.create(
        contrato=contrato,
        indice=indice,
        arquivo_nome=previa.arquivo_nome,
        importado_por=usuario,
        linhas_validas=len(linhas_validas),
        linhas_invalidas=len(problemáticas),
    )
    for linha in problemáticas:
        InconsistenciaImportacao.objects.create(
            importacao_id=importacao,
            numero_linha=linha.numero_linha,
            codigo_lido=linha.codigo,
            caixa_falhou=linha.caixa_falhou or linha.campo_falhou,
            mensagem=linha.mensagem or "Linha não importada por ser inválida.",
        )

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
            documento._history_user = usuario
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
                documento._history_user = usuario
                documento.save(update_fields=campos_alterados)

        codigo = CodigoDocumento.objects.filter(documento=documento, perfil=perfil_modelo).first()
        if codigo is None:
            codigo = CodigoDocumento(
                documento=documento,
                perfil=perfil_modelo,
                codigo=linha.codigo,
            )
            codigo._history_user = usuario
            codigo.save()
        elif codigo.codigo != linha.codigo:
            codigo.codigo = linha.codigo
            codigo._history_user = usuario
            codigo.save(update_fields=("codigo",))

        item = ItemPrevisto.objects.filter(indice=indice, documento=documento).first()
        if item is None:
            item = ItemPrevisto(
                indice=indice,
                documento=documento,
                titulo=linha.titulo,
                excluido=linha.excluido,
            )
            item._history_user = usuario
            item.save()
        elif item.titulo != linha.titulo or item.excluido != linha.excluido:
            item.titulo = linha.titulo
            item.excluido = linha.excluido
            item._history_user = usuario
            item.save(update_fields=("titulo", "excluido"))
        documentos_incluidos.add(documento.pk)

    if not problemáticas:
        itens_removidos = indice.itens.exclude(documento_id__in=documentos_incluidos).select_related("documento")
        for item in itens_removidos:
            item._history_user = usuario
            item.delete()

    return indice


def previstos_vigentes(contrato):
    """Itens não excluídos que compõem a união dos índices vigentes do contrato."""
    return _previstos_sem_duplicatas(contrato)


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
