from collections import defaultdict

from django.db import transaction
from django.db.models import Count, F, Max, Prefetch, Q

from contas.models import Usuario
from contratos.models import Contrato, Participacao, PerfilContrato
from documentos.models import Analise, CodigoDocumento, Documento, Emissao

from .models import Grd, GrdItem


MOTIVO_CODIGO_NAO_ENCONTRADO = "código não encontrado no contrato"
MOTIVO_DOCUMENTO_SEM_EMISSAO = "documento sem emissão"
MOTIVO_DOCUMENTO_CANCELADO = "documento cancelado"


def pode_criar_grd(usuario, contrato):
    return bool(
        usuario.is_active
        and (
            usuario.is_staff
            or usuario.is_superuser
            or Participacao.objects.filter(
                usuario=usuario,
                contrato=contrato,
                ativo=True,
                papel__in=(Usuario.Perfil.ADMIN, Usuario.Perfil.EQUIPE),
            ).exists()
        )
    )


def preparar_grd(contrato, texto_codigos):
    from documentos.servicos import (
        _perfil_vigente,
        _situacao_atual,
        ultima_emissao,
    )

    codigos = []
    vistos = set()
    for linha in (texto_codigos or "").splitlines():
        codigo = linha.strip()
        if codigo and codigo not in vistos:
            vistos.add(codigo)
            codigos.append(codigo)

    if not codigos:
        return {"aceitos": [], "recusados": []}

    perfil_modelo, perfil = _perfil_vigente(contrato)
    analises = Analise.objects.order_by(
        F("data_analise").desc(nulls_last=True), "-registrado_em", "-pk"
    )
    emissoes = Emissao.objects.order_by("data_emissao", "pk").prefetch_related(
        Prefetch("analises", queryset=analises)
    )
    documentos_base = Documento.objects.filter(contrato=contrato)
    documentos = list(
        documentos_base.filter(
            Q(identificador_base__in=codigos) | Q(codigos__codigo__in=codigos)
        )
        .select_related("contrato")
        .prefetch_related(Prefetch("emissoes", queryset=emissoes))
        .distinct()
        .order_by("pk")
    )

    documentos_por_id = {documento.pk: documento for documento in documentos}
    documentos_por_codigo = {
        documento.identificador_base: documento
        for documento in documentos
        if documento.identificador_base in vistos
    }
    codigos_vigentes = CodigoDocumento.objects.filter(
        documento_id__in=documentos_por_id,
        perfil=perfil_modelo,
        codigo__in=codigos,
    ).values_list("codigo", "documento_id")
    for codigo, documento_id in codigos_vigentes:
        documentos_por_codigo.setdefault(codigo, documentos_por_id[documento_id])
    codigos_anteriores = (
        CodigoDocumento.objects.filter(
            documento_id__in=documentos_por_id,
            codigo__in=codigos,
        )
        .exclude(perfil=perfil_modelo)
        .order_by("-perfil__vigencia_inicio", "-perfil__versao", "pk")
        .values_list("codigo", "documento_id")
    )
    for codigo, documento_id in codigos_anteriores:
        documentos_por_codigo.setdefault(codigo, documentos_por_id[documento_id])

    aceitos = []
    recusados = []
    for codigo in codigos:
        documento = documentos_por_codigo.get(codigo)
        if documento is None:
            recusados.append({"codigo": codigo, "motivo": MOTIVO_CODIGO_NAO_ENCONTRADO})
            continue

        _, _, _, grupo = _situacao_atual(documento, perfil)
        if grupo.id.casefold() == "cancelado":
            recusados.append({"codigo": codigo, "motivo": MOTIVO_DOCUMENTO_CANCELADO})
            continue

        emissao = ultima_emissao(documento)
        if emissao is None:
            recusados.append({"codigo": codigo, "motivo": MOTIVO_DOCUMENTO_SEM_EMISSAO})
            continue

        aceitos.append(
            {
                "codigo": codigo,
                "titulo": documento.titulo or "(sem título)",
                "revisao": emissao.revisao,
                "versao": emissao.versao,
                "documento": documento,
                "emissao": emissao,
            }
        )

    return {"aceitos": aceitos, "recusados": recusados}


def criar_grd(contrato, usuario, data, destinatario, observacao, texto_codigos):
    with transaction.atomic():
        contrato_bloqueado = Contrato.objects.select_for_update().get(pk=contrato.pk)
        previa = preparar_grd(contrato_bloqueado, texto_codigos)
        if not previa["aceitos"]:
            return {
                "grd": None,
                "erro": "Nenhum documento aceito; a GRD não foi criada.",
                **previa,
            }

        ultimo_numero = Grd.objects.filter(contrato=contrato_bloqueado).aggregate(
            ultimo=Max("numero")
        )["ultimo"] or 0
        grd = Grd.objects.create(
            contrato=contrato_bloqueado,
            numero=ultimo_numero + 1,
            data=data,
            destinatario=(destinatario or "").strip(),
            observacao=(observacao or "").strip(),
            criado_por=usuario,
        )
        GrdItem.objects.bulk_create(
            [GrdItem(grd=grd, emissao=item["emissao"]) for item in previa["aceitos"]]
        )

    return {"grd": grd, "erro": "", **previa}


def listar_grds(contrato):
    return (
        Grd.objects.filter(contrato=contrato)
        .select_related("contrato", "criado_por")
        .annotate(quantidade_itens=Count("itens"))
        .order_by("-criado_em", "-numero")
    )


def grds_da_emissao(emissao):
    return (
        Grd.objects.filter(itens__emissao=emissao)
        .select_related("contrato", "criado_por")
        .order_by("-criado_em", "-numero")
    )


def grds_por_emissoes(emissoes):
    emissao_ids = [emissao.pk for emissao in emissoes if emissao.pk]
    por_emissao = defaultdict(list)
    if not emissao_ids:
        return por_emissao
    itens = GrdItem.objects.filter(emissao_id__in=emissao_ids).select_related(
        "grd", "grd__contrato", "grd__criado_por"
    ).order_by("-grd__criado_em", "-grd__numero")
    for item in itens:
        por_emissao[item.emissao_id].append(item.grd)
    return por_emissao

