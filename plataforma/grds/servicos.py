from collections import defaultdict
import re

from django.db import transaction
from django.db.models import Count, F, Max, Prefetch, Q

from contas.models import Usuario
from contratos.models import Contrato, Participacao, PerfilContrato
from documentos.models import Analise, CodigoDocumento, Documento, Emissao

from .models import Grd, GrdCampoCabecalho, GrdConfiguracao, GrdItem


MOTIVO_CODIGO_NAO_ENCONTRADO = "código não encontrado no contrato"
MOTIVO_DOCUMENTO_SEM_EMISSAO = "documento sem emissão"
MOTIVO_DOCUMENTO_CANCELADO = "documento cancelado"
SEGMENTOS_CODIGO = (
    ("linha", "Linha"),
    ("trecho", "Trecho"),
    ("subtrecho", "Subtrecho"),
    ("unidade", "Unidade"),
    ("etapa", "Etapa"),
    ("classe", "Classe"),
    ("subclasse", "Subclasse"),
    ("sequencial", "Sequencial"),
)
FORMATOS_COPIA_PADRAO = ["A1", "A3", "A4", "Digital"]


def garantir_configuracao_grd(contrato):
    with transaction.atomic():
        configuracao, criada = GrdConfiguracao.objects.get_or_create(
            contrato=contrato,
            defaults={"formatos_copias": FORMATOS_COPIA_PADRAO},
        )
        campos_padrao = (
            {
                "chave": "obra",
                "habilitado": True,
                "rotulo": "Obra",
                "fonte": GrdCampoCabecalho.Fonte.CONTRATO,
                "valor_contrato": contrato.nome,
                "ordem": 10,
            },
            {
                "chave": "trecho",
                "habilitado": True,
                "rotulo": "Trecho",
                "fonte": GrdCampoCabecalho.Fonte.CODIGO,
                "segmentos_codigo": ["linha", "trecho", "subtrecho", "unidade"],
                "ordem": 20,
            },
            {
                "chave": "ac",
                "habilitado": True,
                "rotulo": "A/C",
                "fonte": GrdCampoCabecalho.Fonte.DIGITADO,
                "ordem": 30,
            },
        )
        for campo in campos_padrao:
            GrdCampoCabecalho.objects.get_or_create(
                configuracao=configuracao,
                chave=campo["chave"],
                defaults=campo,
            )
        if criada:
            configuracao.formatos_copias = FORMATOS_COPIA_PADRAO
            configuracao.save(update_fields=("formatos_copias",))
    return configuracao


def proximo_numero_grd(contrato):
    ultimo = Grd.objects.filter(contrato=contrato).aggregate(ultimo=Max("numero"))["ultimo"]
    return (ultimo or 0) + 1


def formatar_numero_grd(configuracao, numero, data):
    return configuracao.formato_numero.format(
        sigla=configuracao.nome_emitente.strip(), seq=numero, ano=data.year
    )


def _valor_codigo(codigo, segmentos):
    grupos = codigo.split("-")
    partes = grupos[1].split(".") if len(grupos) > 1 else []
    valores = dict(zip((nome for nome, _ in SEGMENTOS_CODIGO), partes))
    etapa_classe = grupos[2] if len(grupos) > 2 else ""
    correspondencia = re.fullmatch(r"(\d)([A-Z])(\d{1,2})", etapa_classe)
    if correspondencia:
        valores.update(
            {
                "etapa": correspondencia.group(1),
                "classe": correspondencia.group(2),
                "subclasse": correspondencia.group(3),
            }
        )
    if len(grupos) > 3:
        valores["sequencial"] = grupos[3]
    partes_selecionadas = [valores.get(segmento, "") for segmento in segmentos]
    return ".".join(parte for parte in partes_selecionadas if parte)


def montar_campos_cabecalho(
    contrato, aceitos, valores_digitados=None, *, configuracao=None, numero=None, data=None
):
    configuracao = configuracao or garantir_configuracao_grd(contrato)
    valores_digitados = valores_digitados or {}
    campos = [
        {"chave": "data", "rotulo": "Data", "valor": data.strftime("%d/%m/%Y") if data else ""},
        {"chave": "quantidade", "rotulo": "Quantidade de documentos", "valor": str(len(aceitos))},
        {
            "chave": "numero",
            "rotulo": "Número",
            "valor": formatar_numero_grd(configuracao, numero, data)
            if numero is not None and data
            else "",
        },
    ]
    codigos = [
        item.get("documento").identificador_base
        for item in aceitos
        if item.get("documento") is not None
    ]
    for campo in configuracao.campos.all():
        if not campo.habilitado:
            continue
        if campo.fonte == GrdCampoCabecalho.Fonte.CONTRATO:
            valor = campo.valor_contrato
        elif campo.fonte == GrdCampoCabecalho.Fonte.CODIGO:
            encontrados = []
            for codigo in codigos:
                valor_codigo = _valor_codigo(codigo, campo.segmentos_codigo)
                if valor_codigo and valor_codigo not in encontrados:
                    encontrados.append(valor_codigo)
            valor = " / ".join(encontrados)
        else:
            valor = valores_digitados.get(str(campo.pk), valores_digitados.get(campo.chave, ""))
        campos.append({"chave": campo.chave, "rotulo": campo.rotulo, "valor": valor or ""})
    return campos


def dados_cabecalho_previa(contrato, previa, data, valores_digitados=None):
    configuracao = garantir_configuracao_grd(contrato)
    numero = proximo_numero_grd(contrato)
    campos = montar_campos_cabecalho(
        contrato,
        previa["aceitos"],
        valores_digitados,
        configuracao=configuracao,
        numero=numero,
        data=data,
    )
    return {
        "campos": campos,
        "numero": numero,
        "numero_formatado": formatar_numero_grd(configuracao, numero, data),
        "formatos_copias": configuracao.formatos_copias or [],
    }


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


def criar_grd(
    contrato,
    usuario,
    data,
    destinatario,
    observacao,
    texto_codigos,
    *,
    valores_digitados=None,
    copias_por_emissao=None,
):
    with transaction.atomic():
        contrato_bloqueado = Contrato.objects.select_for_update().get(pk=contrato.pk)
        previa = preparar_grd(contrato_bloqueado, texto_codigos)
        if not previa["aceitos"]:
            return {
                "grd": None,
                "erro": "Nenhum documento aceito; a GRD não foi criada.",
                **previa,
            }

        configuracao = garantir_configuracao_grd(contrato_bloqueado)
        numero = proximo_numero_grd(contrato_bloqueado)
        campos_cabecalho = montar_campos_cabecalho(
            contrato_bloqueado,
            previa["aceitos"],
            valores_digitados,
            configuracao=configuracao,
            numero=numero,
            data=data,
        )
        nome_completo = usuario.get_full_name().strip() if usuario else ""
        grd = Grd.objects.create(
            contrato=contrato_bloqueado,
            numero=numero,
            numero_formatado=formatar_numero_grd(configuracao, numero, data),
            data=data,
            destinatario=(destinatario or "").strip(),
            observacao=(observacao or "").strip(),
            campos_cabecalho={campo["chave"]: campo["valor"] for campo in campos_cabecalho},
            formatos_copias=configuracao.formatos_copias or [],
            emitido_por_nome=nome_completo,
            criado_por=usuario,
        )
        GrdItem.objects.bulk_create(
            [
                GrdItem(
                    grd=grd,
                    emissao=item["emissao"],
                    copias=(copias_por_emissao or {}).get(item["emissao"].pk, {}),
                )
                for item in previa["aceitos"]
            ]
        )

    return {"grd": grd, "erro": "", **previa}


def listar_grds(contrato):
    return (
        Grd.objects.filter(contrato=contrato)
        .select_related("contrato", "criado_por")
        .annotate(quantidade_itens=Count("itens"))
        .order_by("-criado_em", "-numero")
    )


def pode_configurar_grd(usuario, contrato):
    return bool(
        contrato
        and usuario.is_active
        and (
            usuario.is_staff
            or usuario.is_superuser
            or Participacao.objects.filter(
                usuario=usuario,
                contrato=contrato,
                ativo=True,
                papel=Usuario.Perfil.ADMIN,
            ).exists()
        )
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
